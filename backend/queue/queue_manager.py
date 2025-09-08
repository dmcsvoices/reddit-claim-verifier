"""
Queue Manager - Core orchestration of LLM processing pipeline
"""
import os
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import psycopg
from contextlib import asynccontextmanager

from ..agents.agent_config import AgentFactory, AGENT_CONFIG, agent_metrics
from ..tools.database_write import get_latest_result, get_post_processing_history


# Configuration
QUEUE_CONFIG = {
    "poll_intervals": {
        "triage": 5,      # seconds - fast processing
        "research": 15,   # longer due to web search complexity  
        "response": 10,   # moderate complexity
        "editorial": 5    # fast editing/polishing
    },
    "assignment_timeout": 300,  # 5 minutes before reassignment
    "max_retries": 3,
    "retry_delays": [60, 300, 900],  # exponential backoff (1min, 5min, 15min)
    "dead_letter_threshold": 3
}


class DatabaseManager:
    """Handle database operations for queue management"""
    
    def __init__(self):
        self.connection_params = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "dbname": os.getenv("DB_NAME", "redditmon"),
            "user": os.getenv("DB_USER", "redditmon"),
            "password": os.getenv("DB_PASSWORD", "supersecret")
        }
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection with proper cleanup"""
        conn = None
        try:
            conn = psycopg.connect(**self.connection_params)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()
    
    async def get_pending_posts(self, stage: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get pending posts for a specific stage"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, reddit_id, title, author, created_utc, url, body, 
                           queue_stage, queue_status, retry_count, metadata
                    FROM posts 
                    WHERE queue_stage = %s 
                      AND queue_status = 'pending'
                      AND (assigned_to IS NULL OR assigned_at < NOW() - INTERVAL %s)
                    ORDER BY COALESCE(metadata->>'priority', '5')::int DESC, 
                             created_utc ASC
                    LIMIT %s
                """, (stage, f"{QUEUE_CONFIG['assignment_timeout']} seconds", limit))
                
                posts = []
                for row in cur.fetchall():
                    post_data = {
                        "id": row[0],
                        "reddit_id": row[1], 
                        "title": row[2],
                        "author": row[3],
                        "created_utc": row[4],
                        "url": row[5],
                        "body": row[6],
                        "queue_stage": row[7],
                        "queue_status": row[8],
                        "retry_count": row[9],
                        "metadata": row[10] or {}
                    }
                    posts.append(post_data)
                
                return posts
    
    async def assign_post_to_worker(self, post_id: int, worker_id: str) -> bool:
        """Assign a post to a worker"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE posts 
                    SET queue_status = 'processing',
                        assigned_to = %s,
                        assigned_at = NOW()
                    WHERE id = %s 
                      AND queue_status = 'pending'
                      AND (assigned_to IS NULL OR assigned_at < NOW() - INTERVAL %s)
                    RETURNING id
                """, (worker_id, post_id, f"{QUEUE_CONFIG['assignment_timeout']} seconds"))
                
                result = cur.fetchone()
                if result:
                    conn.commit()
                    return True
                else:
                    conn.rollback()
                    return False
    
    async def clear_assignment(self, post_id: int):
        """Clear assignment after processing completion"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE posts 
                    SET assigned_to = NULL,
                        assigned_at = NULL,
                        processed_at = NOW()
                    WHERE id = %s
                """, (post_id,))
                conn.commit()
    
    async def update_post_status(self, post_id: int, status: str, retry_count: int = None):
        """Update post processing status"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                if retry_count is not None:
                    cur.execute("""
                        UPDATE posts 
                        SET queue_status = %s,
                            retry_count = %s,
                            assigned_to = NULL,
                            assigned_at = NULL,
                            processed_at = NOW()
                        WHERE id = %s
                    """, (status, retry_count, post_id))
                else:
                    cur.execute("""
                        UPDATE posts 
                        SET queue_status = %s,
                            assigned_to = NULL,
                            assigned_at = NULL,
                            processed_at = NOW()
                        WHERE id = %s
                    """, (status, post_id))
                conn.commit()
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get current queue statistics"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        queue_stage,
                        queue_status,
                        COUNT(*) as count
                    FROM posts 
                    WHERE queue_stage IN ('triage', 'research', 'response', 'editorial', 'post_queue')
                    GROUP BY queue_stage, queue_status
                    ORDER BY queue_stage, queue_status
                """)
                
                stats = {}
                for stage, status, count in cur.fetchall():
                    if stage not in stats:
                        stats[stage] = {}
                    stats[stage][status] = count
                
                return stats


class QueueManager:
    """Main queue management system"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.agents = {}  # Will hold persistent agent instances
        self.workers = {}  # Will hold worker tasks
        self.running = False
        self.worker_id_counter = 0
        
        # Initialize agents
        self._initialize_agents()
        
        # Track endpoint status
        self.endpoint_status = {
            stage: {
                "available": True, 
                "current_load": 0, 
                "max_concurrent": config["max_concurrent"]
            }
            for stage, config in AGENT_CONFIG.items()
        }
    
    def _initialize_agents(self):
        """Initialize persistent agent instances"""
        for stage in AGENT_CONFIG.keys():
            try:
                self.agents[stage] = AgentFactory.create_agent(stage)
                print(f"Initialized {stage} agent: {self.agents[stage].__class__.__name__}")
            except Exception as e:
                print(f"Failed to initialize {stage} agent: {e}")
                self.endpoint_status[stage]["available"] = False
    
    async def get_processing_context(self, post_id: int, current_stage: str) -> Dict[str, Any]:
        """Get all previous processing results for context"""
        previous_stages = {
            "research": ["triage"],
            "response": ["triage", "research"], 
            "editorial": ["triage", "research", "response"]
        }
        
        context = {}
        for stage in previous_stages.get(current_stage, []):
            result = await get_latest_result(post_id, stage)
            if result:
                context[f"{stage}_result"] = result
        
        return context
    
    def can_process_more(self, stage: str) -> bool:
        """Check if stage can process more posts"""
        status = self.endpoint_status[stage]
        return (status["available"] and 
                status["current_load"] < status["max_concurrent"])
    
    def get_available_slots(self, stage: str) -> int:
        """Get number of available processing slots for stage"""
        status = self.endpoint_status[stage]
        if not status["available"]:
            return 0
        return max(0, status["max_concurrent"] - status["current_load"])
    
    async def process_post(self, post_data: Dict[str, Any], stage: str) -> Dict[str, Any]:
        """Process a single post through a stage"""
        post_id = post_data["id"]
        worker_id = f"{stage}-worker-{self.worker_id_counter}"
        self.worker_id_counter += 1
        
        start_time = time.time()
        
        try:
            # Assign post to worker
            assigned = await self.db.assign_post_to_worker(post_id, worker_id)
            if not assigned:
                return {"success": False, "error": "Failed to assign post to worker"}
            
            # Update load tracking
            self.endpoint_status[stage]["current_load"] += 1
            
            # Get processing context
            context = await self.get_processing_context(post_id, stage)
            
            # Process with agent
            agent = self.agents[stage]
            result = await agent.process(post_data, context)
            
            # Handle completion
            await self.handle_agent_completion(post_id, stage, result)
            
            # Record metrics
            processing_time = time.time() - start_time
            success = result.get("success", False)
            token_count = result.get("usage", {}).get("total_tokens", 0)
            
            agent_metrics.record_request(stage, success, processing_time, token_count)
            
            return result
            
        except Exception as e:
            # Handle processing error
            await self.handle_processing_error(post_id, stage, str(e))
            
            processing_time = time.time() - start_time
            agent_metrics.record_request(stage, False, processing_time, 0)
            
            return {"success": False, "error": f"Processing failed: {str(e)}"}
            
        finally:
            # Always decrement load counter
            self.endpoint_status[stage]["current_load"] = max(
                0, self.endpoint_status[stage]["current_load"] - 1
            )
    
    async def handle_agent_completion(self, post_id: int, stage: str, agent_result: Dict[str, Any]):
        """Handle completion of agent processing"""
        
        if not agent_result.get("success"):
            # Handle failure - this will be caught by process_post error handling
            return
        
        # Check if agent wrote to database via tools
        tool_calls = agent_result.get("tool_calls", [])
        database_writes = [tc for tc in tool_calls if tc["tool"] == "write_to_database"]
        
        if database_writes:
            # Agent handled status update via database_write_tool
            # Queue manager just needs to clear assignment
            await self.db.clear_assignment(post_id)
            
            # Log successful tool usage
            for db_write in database_writes:
                write_result = db_write.get("result", {})
                if write_result.get("success"):
                    print(f"Stage {stage} completed for post {post_id}, advanced to: {write_result.get('next_stage', 'completed')}")
        else:
            # No database write - mark as completed but don't advance
            await self.db.update_post_status(post_id, "completed")
            print(f"Stage {stage} completed for post {post_id} (no advancement)")
    
    async def handle_processing_error(self, post_id: int, stage: str, error: str):
        """Handle processing errors with retry logic"""
        # Get current retry count
        posts = await self.db.get_pending_posts(stage, limit=1000)  # Get all to find this post
        current_post = next((p for p in posts if p["id"] == post_id), None)
        
        if not current_post:
            # Post not found, log error
            print(f"Error processing post {post_id} in stage {stage}: {error}")
            await self.db.update_post_status(post_id, "failed")
            return
        
        retry_count = current_post.get("retry_count", 0) + 1
        
        if retry_count <= QUEUE_CONFIG["max_retries"]:
            # Schedule retry
            await self.db.update_post_status(post_id, "pending", retry_count)
            print(f"Post {post_id} failed in stage {stage} (attempt {retry_count}), will retry: {error}")
            
            # Add delay before retry (handled by next poll cycle)
            
        else:
            # Move to dead letter queue
            await self.db.update_post_status(post_id, "failed")
            print(f"Post {post_id} failed permanently in stage {stage} after {retry_count} attempts: {error}")
    
    async def process_stage_queue(self, stage: str):
        """Main worker loop for processing a stage queue"""
        print(f"Starting {stage} stage worker")
        
        while self.running:
            try:
                # Check if we can process more
                if not self.can_process_more(stage):
                    await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])
                    continue
                
                # Get available processing slots
                available_slots = self.get_available_slots(stage)
                if available_slots <= 0:
                    await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])
                    continue
                
                # Get pending posts
                posts = await self.db.get_pending_posts(stage, limit=available_slots)
                
                if not posts:
                    await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])
                    continue
                
                # Process posts concurrently
                tasks = []
                for post in posts:
                    task = asyncio.create_task(self.process_post(post, stage))
                    tasks.append(task)
                
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Log any exceptions
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            print(f"Task exception in {stage}: {result}")
                
            except Exception as e:
                print(f"Error in {stage} worker loop: {e}")
                await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])
            
            # Wait before next poll
            await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])
        
        print(f"Stopped {stage} stage worker")
    
    async def start(self):
        """Start all queue processing workers"""
        if self.running:
            return
        
        self.running = True
        print("Starting Queue Manager...")
        
        # Start worker for each stage
        for stage in AGENT_CONFIG.keys():
            if self.endpoint_status[stage]["available"]:
                worker_task = asyncio.create_task(self.process_stage_queue(stage))
                self.workers[stage] = worker_task
                print(f"Started worker for {stage} stage")
            else:
                print(f"Skipping {stage} stage - endpoint unavailable")
        
        print(f"Queue Manager started with {len(self.workers)} workers")
    
    async def stop(self):
        """Stop all queue processing workers"""
        if not self.running:
            return
        
        self.running = False
        print("Stopping Queue Manager...")
        
        # Cancel all worker tasks
        for stage, task in self.workers.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            print(f"Stopped worker for {stage} stage")
        
        self.workers.clear()
        print("Queue Manager stopped")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current queue manager status"""
        queue_stats = await self.db.get_queue_stats()
        
        return {
            "running": self.running,
            "workers": list(self.workers.keys()),
            "endpoint_status": self.endpoint_status.copy(),
            "queue_stats": queue_stats,
            "agent_metrics": agent_metrics.get_metrics(),
            "config": QUEUE_CONFIG
        }


# Global queue manager instance
queue_manager = QueueManager()


# Utility functions for FastAPI integration
async def start_queue_manager():
    """Start the global queue manager"""
    await queue_manager.start()


async def stop_queue_manager():
    """Stop the global queue manager"""
    await queue_manager.stop()


async def get_queue_status():
    """Get queue manager status"""
    return await queue_manager.get_status()