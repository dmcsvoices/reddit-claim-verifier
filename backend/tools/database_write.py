"""
Database Write Tool for Content Generation Agents
Allows LLM agents to write their results back to the queue database
"""
import json
import psycopg
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from ..main import get_db_connection


class DatabaseWriteTool:
    def __init__(self):
        pass
    
    @staticmethod
    def get_tool_definition() -> Dict[str, Any]:
        """Return the Ollama tool definition for database writing"""
        return {
            "type": "function", 
            "function": {
                "name": "write_to_database",
                "description": "Write processed content to the database queue system",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "post_id": {
                            "type": "integer",
                            "description": "The ID of the Reddit post being processed"
                        },
                        "stage": {
                            "type": "string", 
                            "description": "Current processing stage",
                            "enum": ["triage", "research", "response", "editorial"]
                        },
                        "content": {
                            "type": "object",
                            "description": "The content to write to database",
                            "properties": {
                                "result": {
                                    "type": "string",
                                    "description": "Main result content (required)"
                                },
                                "confidence": {
                                    "type": "number",
                                    "description": "Confidence score (0.0-1.0)",
                                    "minimum": 0.0,
                                    "maximum": 1.0
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "Brief summary of the result"
                                },
                                "claims_identified": {
                                    "type": "array",
                                    "description": "List of factual claims identified (for triage stage)",
                                    "items": {"type": "string"}
                                },
                                "sources": {
                                    "type": "array",
                                    "description": "Sources used in research or verification",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "url": {"type": "string"},
                                            "title": {"type": "string"},
                                            "credibility": {"type": "string"}
                                        }
                                    }
                                },
                                "fact_check_status": {
                                    "type": "string",
                                    "description": "Status of fact checking: true, false, mixed, unverifiable",
                                    "enum": ["true", "false", "mixed", "unverifiable", "pending"]
                                },
                                "reasoning": {
                                    "type": "string",
                                    "description": "Reasoning behind the conclusion"
                                },
                                "tags": {
                                    "type": "array",
                                    "description": "Tags for categorization",
                                    "items": {"type": "string"}
                                },
                                "metadata": {
                                    "type": "object",
                                    "description": "Additional stage-specific metadata"
                                }
                            },
                            "required": ["result"]
                        },
                        "next_stage": {
                            "type": "string",
                            "description": "Next stage to advance to, or null to stop processing",
                            "enum": ["research", "response", "editorial", "post_queue", "completed", "rejected"]
                        },
                        "priority": {
                            "type": "integer",
                            "description": "Processing priority (1-10, higher is more urgent)",
                            "minimum": 1,
                            "maximum": 10,
                            "default": 5
                        }
                    },
                    "required": ["post_id", "stage", "content"]
                }
            }
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Write processing results to database"""
        post_id = kwargs.get("post_id")
        stage = kwargs.get("stage")
        content = kwargs.get("content")
        next_stage = kwargs.get("next_stage")
        priority = kwargs.get("priority", 5)
        
        # Validate required parameters
        if not post_id:
            return {"success": False, "error": "post_id is required"}
        if not stage:
            return {"success": False, "error": "stage is required"}
        if not content or not isinstance(content, dict):
            return {"success": False, "error": "content object is required"}
        if "result" not in content:
            return {"success": False, "error": "content.result is required"}
        
        # Validate stage
        valid_stages = ["triage", "research", "response", "editorial"]
        if stage not in valid_stages:
            return {"success": False, "error": f"Invalid stage. Must be one of: {valid_stages}"}
        
        # Validate next_stage if provided
        valid_next_stages = ["research", "response", "editorial", "post_queue", "completed", "rejected"]
        if next_stage and next_stage not in valid_next_stages:
            return {"success": False, "error": f"Invalid next_stage. Must be one of: {valid_next_stages}"}
        
        try:
            conn = get_db_connection()
            
            with conn.cursor() as cur:
                # First, verify the post exists
                cur.execute("SELECT id FROM posts WHERE id = %s", (post_id,))
                if not cur.fetchone():
                    return {"success": False, "error": f"Post with ID {post_id} not found"}
                
                # Prepare the full result data
                result_data = {
                    "stage": stage,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "content": content,
                    "priority": priority
                }
                
                # Insert the result
                cur.execute("""
                    INSERT INTO queue_results (post_id, stage, result)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (post_id, stage, json.dumps(result_data)))
                
                result_id = cur.fetchone()[0]
                
                # Update post status and advance to next stage
                if next_stage:
                    if next_stage in ["completed", "rejected"]:
                        # Final states
                        cur.execute("""
                            UPDATE posts 
                            SET queue_stage = %s,
                                queue_status = %s,
                                processed_at = NOW(),
                                assigned_to = NULL,
                                assigned_at = NULL
                            WHERE id = %s
                        """, (next_stage, next_stage, post_id))
                    else:
                        # Move to next processing stage
                        cur.execute("""
                            UPDATE posts 
                            SET queue_stage = %s, 
                                queue_status = 'pending',
                                processed_at = NOW(),
                                assigned_to = NULL,
                                assigned_at = NULL,
                                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                            WHERE id = %s
                        """, (next_stage, json.dumps({"priority": priority}), post_id))
                else:
                    # Just mark current stage as completed
                    cur.execute("""
                        UPDATE posts 
                        SET queue_status = 'completed',
                            processed_at = NOW(),
                            assigned_to = NULL,
                            assigned_at = NULL
                        WHERE id = %s
                    """, (post_id,))
                
                conn.commit()
                
                return {
                    "success": True, 
                    "message": f"Successfully saved {stage} result for post {post_id}",
                    "result_id": result_id,
                    "next_stage": next_stage,
                    "post_id": post_id,
                    "stage": stage
                }
                
        except psycopg.Error as e:
            if conn:
                conn.rollback()
            return {
                "success": False, 
                "error": f"Database error: {str(e)}",
                "post_id": post_id,
                "stage": stage
            }
        except json.JSONEncodeError as e:
            return {
                "success": False,
                "error": f"JSON encoding error: {str(e)}",
                "post_id": post_id,
                "stage": stage
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {
                "success": False, 
                "error": f"Unexpected error: {str(e)}",
                "post_id": post_id,
                "stage": stage
            }
        finally:
            if conn:
                conn.close()


# Tool function for direct use in agent implementations
async def write_to_database(**kwargs) -> Dict[str, Any]:
    """Direct function interface for database write tool"""
    tool = DatabaseWriteTool()
    return await tool.execute(**kwargs)


# Utility function to get the latest result for a post/stage
async def get_latest_result(post_id: int, stage: str) -> Optional[Dict[str, Any]]:
    """Get the most recent result for a post at a specific stage"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT result FROM queue_results 
                WHERE post_id = %s AND stage = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (post_id, stage))
            
            result = cur.fetchone()
            if result:
                return json.loads(result[0])
            return None
            
    except Exception as e:
        print(f"Error getting latest result: {e}")
        return None
    finally:
        if conn:
            conn.close()


# Utility function to get all results for a post
async def get_post_processing_history(post_id: int) -> Dict[str, Any]:
    """Get complete processing history for a post"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT stage, result, created_at 
                FROM queue_results 
                WHERE post_id = %s 
                ORDER BY created_at ASC
            """, (post_id,))
            
            results = cur.fetchall()
            history = {}
            
            for stage, result_json, created_at in results:
                if stage not in history:
                    history[stage] = []
                
                result_data = json.loads(result_json)
                result_data["created_at"] = created_at.isoformat()
                history[stage].append(result_data)
            
            return history
            
    except Exception as e:
        print(f"Error getting processing history: {e}")
        return {}
    finally:
        if conn:
            conn.close()


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_database_write():
        tool = DatabaseWriteTool()
        
        # Test writing triage result
        result = await tool.execute(
            post_id=1,
            stage="triage",
            content={
                "result": "This post contains factual claims about climate change that should be researched.",
                "confidence": 0.85,
                "claims_identified": [
                    "Global temperatures have increased by 2°C since 1900",
                    "Arctic ice is melting faster than predicted"
                ],
                "fact_check_status": "pending",
                "reasoning": "Post makes specific numeric claims about climate data"
            },
            next_stage="research",
            priority=7
        )
        
        print("Test result:", json.dumps(result, indent=2))
    
    # Print tool definition
    print("Tool definition:", json.dumps(DatabaseWriteTool.get_tool_definition(), indent=2))