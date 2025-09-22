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

import sys
from pathlib import Path

# Add backend directory to Python path for imports
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from agents.agent_config import AgentFactory, AGENT_CONFIG, agent_metrics
from tools.database_write import get_latest_result, get_post_processing_history


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
        """Get pending posts for a specific stage, respecting retry timeouts"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Get retry timeout from settings
                cur.execute("SELECT setting_value FROM queue_settings WHERE setting_key = 'retry_timeout_seconds'")
                retry_timeout_result = cur.fetchone()
                retry_timeout = int(retry_timeout_result[0]) if retry_timeout_result else 300

                timeout_seconds = QUEUE_CONFIG['assignment_timeout']
                cur.execute("""
                    SELECT id, reddit_id, title, author, created_utc, url, body,
                           queue_stage, queue_status, retry_count, metadata,
                           last_retry_at, last_error_message
                    FROM posts
                    WHERE queue_stage = %s
                      AND queue_status = 'pending'
                      AND (assigned_to IS NULL OR assigned_at < NOW() - MAKE_INTERVAL(secs => %s))
                      AND (last_retry_at IS NULL OR last_retry_at < NOW() - MAKE_INTERVAL(secs => %s))
                    ORDER BY COALESCE(metadata->>'priority', '5')::int DESC,
                             retry_count ASC,
                             created_utc ASC
                    LIMIT %s
                """, (stage, timeout_seconds, retry_timeout, limit))
                
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
                        "metadata": row[10] or {},
                        "last_retry_at": row[11],
                        "last_error_message": row[12]
                    }
                    posts.append(post_data)
                
                return posts
    
    async def assign_post_to_worker(self, post_id: int, worker_id: str) -> bool:
        """Assign a post to a worker"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                timeout_seconds = QUEUE_CONFIG['assignment_timeout']
                cur.execute("""
                    UPDATE posts
                    SET queue_status = 'processing',
                        assigned_to = %s,
                        assigned_at = NOW(),
                        processing_started_at = NOW()
                    WHERE id = %s
                      AND queue_status = 'pending'
                      AND (assigned_to IS NULL OR assigned_at < NOW() - MAKE_INTERVAL(secs => %s))
                    RETURNING id
                """, (worker_id, post_id, timeout_seconds))
                
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
    
    async def update_post_status(self, post_id: int, status: str, retry_count: int = None, error_message: str = None):
        """Update post processing status with error tracking"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                if retry_count is not None:
                    cur.execute("""
                        UPDATE posts
                        SET queue_status = %s,
                            retry_count = %s,
                            assigned_to = NULL,
                            assigned_at = NULL,
                            processing_started_at = NULL,
                            processed_at = NOW(),
                            last_error_message = COALESCE(%s, last_error_message),
                            last_retry_at = CASE WHEN %s = 'pending' THEN NOW() ELSE last_retry_at END
                        WHERE id = %s
                    """, (status, retry_count, error_message, status, post_id))
                else:
                    cur.execute("""
                        UPDATE posts
                        SET queue_status = %s,
                            assigned_to = NULL,
                            assigned_at = NULL,
                            processing_started_at = NULL,
                            processed_at = NOW(),
                            last_error_message = COALESCE(%s, last_error_message)
                        WHERE id = %s
                    """, (status, error_message, post_id))
                conn.commit()
    
    async def is_stage_paused(self, stage: str) -> bool:
        """Check if a queue stage is paused"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT is_paused
                    FROM queue_state
                    WHERE stage = %s
                """, (stage,))

                result = cur.fetchone()
                return result[0] if result else False

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

    async def process_scheduled_retries(self) -> int:
        """Process posts that are scheduled for retry and mark fallback events as resolved"""
        async with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Find posts that are ready for retry based on fallback_events
                cur.execute("""
                    SELECT DISTINCT fe.post_id, p.queue_stage
                    FROM fallback_events fe
                    JOIN posts p ON fe.post_id = p.id
                    WHERE fe.status = 'active'
                    AND fe.retry_scheduled_for IS NOT NULL
                    AND fe.retry_scheduled_for <= NOW()
                    AND p.queue_status != 'pending'
                """)

                ready_posts = cur.fetchall()
                processed_count = 0

                for post_id, current_stage in ready_posts:
                    try:
                        # Reset post to pending status for retry
                        cur.execute("""
                            UPDATE posts
                            SET queue_status = 'pending',
                                updated_at = NOW()
                            WHERE id = %s
                        """, (post_id,))

                        # Mark related fallback events as resolved
                        cur.execute("""
                            UPDATE fallback_events
                            SET status = 'resolved',
                                resolved_at = NOW()
                            WHERE post_id = %s
                            AND status = 'active'
                            AND retry_scheduled_for <= NOW()
                        """, (post_id,))

                        processed_count += 1
                        print(f"   ⏰ Retrying post {post_id} in {current_stage} stage after scheduled delay")

                    except Exception as e:
                        print(f"   ❌ Failed to retry post {post_id}: {e}")
                        continue

                if processed_count > 0:
                    conn.commit()

                return processed_count


class QueueManager:
    """Main queue management system"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.agents = {}  # Will hold persistent agent instances
        self.workers = {}  # Will hold worker tasks
        self.running = False
        self.worker_id_counter = 0

        # Track endpoint status - MUST be initialized before _initialize_agents()
        self.endpoint_status = {
            stage: {
                "available": True,
                "current_load": 0,
                "max_concurrent": config["max_concurrent"]
            }
            for stage, config in AGENT_CONFIG.items()
        }

        # Initialize agents
        self._initialize_agents()
    
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
        reddit_id_short = post_data["reddit_id"][:8] + "..."

        print(f"🔧 {worker_id}: attempting to assign post {post_id} ({reddit_id_short})")

        try:
            # Assign post to worker
            assigned = await self.db.assign_post_to_worker(post_id, worker_id)
            if not assigned:
                print(f"❌ {worker_id}: failed to assign post {post_id} (already taken)")
                return {"success": False, "error": "Failed to assign post to worker"}

            print(f"✅ {worker_id}: successfully assigned post {post_id} ({reddit_id_short})")

            # Update load tracking
            old_load = self.endpoint_status[stage]["current_load"]
            self.endpoint_status[stage]["current_load"] += 1
            new_load = self.endpoint_status[stage]["current_load"]
            print(f"📊 {stage} load: {old_load} → {new_load}")

            # Get processing context
            context = await self.get_processing_context(post_id, stage)
            context_info = ", ".join(context.keys()) if context else "none"
            print(f"📋 {worker_id}: context loaded - {context_info}")

            # Process with agent
            agent = self.agents[stage]
            print(f"🤖 {worker_id}: starting {agent.__class__.__name__} processing")
            result = await agent.process(post_data, context)

            processing_time = time.time() - start_time
            success = result.get("success", False)

            if success:
                print(f"✅ {worker_id}: processing completed successfully in {processing_time:.2f}s")
            else:
                error_msg = result.get("error", "unknown error")
                print(f"❌ {worker_id}: processing failed in {processing_time:.2f}s - {error_msg}")

            # Handle completion
            await self.handle_agent_completion(post_id, stage, result)

            # Record metrics
            try:
                usage = result.get("usage", {})
                if isinstance(usage, dict):
                    token_count = usage.get("total_tokens", 0)
                else:
                    # Handle Together AI UsageData object
                    token_count = getattr(usage, 'total_tokens', 0)

                if token_count > 0:
                    print(f"📈 {worker_id}: used {token_count} tokens")
            except Exception as e:
                print(f"⚠️  Could not extract token usage: {e}")
                token_count = 0

            agent_metrics.record_request(stage, success, processing_time, token_count)

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            print(f"💥 {worker_id}: exception during processing after {processing_time:.2f}s - {str(e)}")

            # Handle processing error
            await self.handle_processing_error(post_id, stage, str(e))

            agent_metrics.record_request(stage, False, processing_time, 0)

            return {"success": False, "error": f"Processing failed: {str(e)}"}

        finally:
            # Always decrement load counter
            old_load = self.endpoint_status[stage]["current_load"]
            self.endpoint_status[stage]["current_load"] = max(
                0, self.endpoint_status[stage]["current_load"] - 1
            )
            new_load = self.endpoint_status[stage]["current_load"]
            print(f"📊 {stage} load: {old_load} → {new_load} (worker {worker_id} finished)")
    
    async def handle_agent_completion(self, post_id: int, stage: str, agent_result: Dict[str, Any]):
        """Handle completion of agent processing"""

        if not agent_result.get("success"):
            # Handle failure with retry logic
            error_msg = agent_result.get("error", "Agent processing failed")
            print(f"🚫 Post {post_id}: agent result marked as failed, skipping completion handling")
            await self.handle_processing_error(post_id, stage, error_msg)
            return

        # Check if agent wrote to database via tools
        tool_calls = agent_result.get("tool_calls", [])
        database_writes = [tc for tc in tool_calls if tc["tool"] == "write_to_database"]

        if database_writes:
            # Agent handled status update via database_write_tool
            print(f"🔧 Post {post_id}: agent used {len(database_writes)} database write(s)")

            # Queue manager just needs to clear assignment
            await self.db.clear_assignment(post_id)

            # Log successful tool usage
            for db_write in database_writes:
                write_result = db_write.get("result", {})
                if write_result.get("success"):
                    next_stage = write_result.get('next_stage', 'completed')
                    print(f"🎯 Post {post_id}: {stage} → {next_stage}")
                else:
                    print(f"❌ Post {post_id}: database write failed - {write_result.get('error', 'unknown error')}")
        else:
            # No database write - mark as completed but don't advance
            await self.db.update_post_status(post_id, "completed")
            print(f"✅ Post {post_id}: {stage} completed (no advancement)")
    
    async def handle_processing_error(self, post_id: int, stage: str, error: str):
        """Handle processing errors with configurable retry logic"""
        async with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                # Get max retry attempts from settings
                cur.execute("SELECT setting_value FROM queue_settings WHERE setting_key = 'max_retry_attempts'")
                max_retries_result = cur.fetchone()
                max_retries = int(max_retries_result[0]) if max_retries_result else 3

                # Get current post info
                cur.execute("SELECT retry_count FROM posts WHERE id = %s", (post_id,))
                post_result = cur.fetchone()

                if not post_result:
                    # Post not found, log error
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"❌ [{timestamp}] Error processing post {post_id} in stage {stage}: {error}")
                    await self.update_post_status(post_id, "failed", error_message=error)
                    return

                current_retry_count = post_result[0] or 0
                new_retry_count = current_retry_count + 1

                if new_retry_count <= max_retries:
                    # Schedule retry
                    await self.update_post_status(post_id, "pending", new_retry_count, error)
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"🔄 [{timestamp}] Post {post_id} failed in {stage} (attempt {new_retry_count}/{max_retries}), will retry: {error}")
                else:
                    # Move to failed status
                    await self.update_post_status(post_id, "failed", new_retry_count, error)
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"💀 [{timestamp}] Post {post_id} failed permanently in {stage} after {new_retry_count} attempts: {error}")
    
    async def process_stage_queue(self, stage: str):
        """Main worker loop for processing a stage queue"""
        print(f"🚀 Starting {stage} stage worker")
        poll_count = 0

        while self.running:
            try:
                poll_count += 1

                # Check if stage is paused
                is_paused = await self.db.is_stage_paused(stage)
                if is_paused:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"⏸️  [{timestamp}] {stage} queue: PAUSED (poll #{poll_count})")
                    await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])
                    continue

                # Check for scheduled retries (only do this for triage stage to avoid duplicate processing)
                if stage == "triage" and poll_count % 10 == 0:  # Check every 10 polls
                    try:
                        retry_count = await self.db.process_scheduled_retries()
                        if retry_count > 0:
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            print(f"⏰ [{timestamp}] Processed {retry_count} scheduled retries")
                    except Exception as e:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"❌ [{timestamp}] Failed to process scheduled retries: {e}")

                # Show regular polling activity
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"🔍 [{timestamp}] {stage} queue: polling for work (poll #{poll_count})")

                # Check if we can process more
                if not self.can_process_more(stage):
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"🔒 [{timestamp}] {stage} queue: endpoint unavailable (poll #{poll_count})")
                    await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])
                    continue

                # Get available processing slots
                available_slots = self.get_available_slots(stage)
                if available_slots <= 0:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"🚦 [{timestamp}] {stage} queue: no available slots (poll #{poll_count})")
                    await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])
                    continue

                # Get pending posts
                posts = await self.db.get_pending_posts(stage, limit=available_slots)

                if not posts:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"📭 [{timestamp}] {stage} queue: no pending posts (poll #{poll_count})")
                    await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])
                    continue

                # Found posts to process
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"📋 [{timestamp}] {stage} queue: found {len(posts)} posts to process (slots: {available_slots})")

                # Process posts concurrently
                tasks = []
                for post in posts:
                    task = asyncio.create_task(self.process_post(post, stage))
                    tasks.append(task)
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"⚡ [{timestamp}] {stage} queue: assigned post {post['id']} ({post['reddit_id'][:8]}...) to worker")

                if tasks:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"🔄 [{timestamp}] {stage} queue: processing {len(tasks)} posts concurrently")
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Log results and exceptions
                    successful = 0
                    failed = 0
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            failed += 1
                            print(f"❌ {stage} queue: task exception - {result}")
                        elif result and result.get("success"):
                            successful += 1
                        else:
                            failed += 1

                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"✅ [{timestamp}] {stage} queue: batch complete - {successful} successful, {failed} failed")

            except Exception as e:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"💥 [{timestamp}] {stage} queue: worker loop error - {e}")
                await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])

            # Wait before next poll
            await asyncio.sleep(QUEUE_CONFIG["poll_intervals"][stage])

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"🛑 [{timestamp}] Stopped {stage} stage worker")
    
    async def start(self):
        """Start all queue processing workers"""
        if self.running:
            print("⚠️ Queue Manager already running, ignoring start request")
            return

        self.running = True
        print("🚀 Starting Queue Manager...")

        # Start worker for each stage
        for stage in AGENT_CONFIG.keys():
            if self.endpoint_status[stage]["available"]:
                worker_task = asyncio.create_task(self.process_stage_queue(stage))
                self.workers[stage] = worker_task
                max_concurrent = self.endpoint_status[stage]["max_concurrent"]
                poll_interval = QUEUE_CONFIG["poll_intervals"][stage]
                print(f"✅ Started {stage} worker (max_concurrent={max_concurrent}, poll_interval={poll_interval}s)")
            else:
                print(f"⚠️ Skipping {stage} stage - endpoint unavailable")

        print(f"🎯 Queue Manager started with {len(self.workers)} active workers")
    
    async def stop(self):
        """Stop all queue processing workers"""
        if not self.running:
            print("⚠️ Queue Manager not running, ignoring stop request")
            return

        self.running = False
        print("🛑 Stopping Queue Manager...")

        # Cancel all worker tasks
        for stage, task in self.workers.items():
            print(f"🔄 Cancelling {stage} worker...")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            print(f"✅ Stopped {stage} worker")

        self.workers.clear()
        print("🏁 Queue Manager stopped completely")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current queue manager status"""
        queue_stats = await self.db.get_queue_stats()

        # Get current pause states for all stages
        queue_states = {}
        for stage in ["triage", "research", "response", "editorial"]:
            is_paused = await self.db.is_stage_paused(stage)
            queue_states[stage] = is_paused

        return {
            "running": self.running,
            "workers": list(self.workers.keys()),
            "endpoint_status": self.endpoint_status.copy(),
            "queue_stats": queue_stats,
            "queue_states": queue_states,
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