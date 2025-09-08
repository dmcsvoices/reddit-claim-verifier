import os
import psycopg
import praw
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Import queue management system
from .queue.queue_manager import start_queue_manager, stop_queue_manager, get_queue_status

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager"""
    # Startup
    print("Starting Reddit Claim Verifier with Queue Management...")
    await start_queue_manager()
    yield
    # Shutdown
    print("Shutting down Queue Management...")
    await stop_queue_manager()

app = FastAPI(title="Reddit Claim Verifier", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class ScanRequest(BaseModel):
    subreddit: str
    hours: int = 4

# Reddit client setup
def get_reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("REDDIT_USER_AGENT", "reddit-claim-verifier/1.0")
    )

def get_db_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "redditmon"),
        user=os.getenv("DB_USER", "redditmon"),
        password=os.getenv("DB_PASSWORD", "supersecret")
    )

@app.on_event("startup")
def startup():
    # Create tables for queue management
    conn = get_db_connection()
    with conn.cursor() as cur:
        # Enhanced posts table with queue management columns
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                reddit_id TEXT UNIQUE NOT NULL,
                title TEXT,
                author TEXT,
                created_utc TIMESTAMPTZ,
                url TEXT,
                body TEXT,
                inserted_at TIMESTAMPTZ DEFAULT NOW(),
                -- Queue management columns
                queue_stage VARCHAR(20) DEFAULT 'triage',
                queue_status VARCHAR(20) DEFAULT 'pending',
                assigned_to VARCHAR(50) NULL,
                assigned_at TIMESTAMPTZ NULL,
                processed_at TIMESTAMPTZ NULL,
                retry_count INTEGER DEFAULT 0,
                metadata JSONB DEFAULT '{}'
            )
        """)
        
        # Queue results table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS queue_results (
                id SERIAL PRIMARY KEY,
                post_id INTEGER REFERENCES posts(id),
                stage VARCHAR(20) NOT NULL,
                result JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # LLM endpoints tracking table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS llm_endpoints (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL,
                url VARCHAR(200) NOT NULL,
                capabilities JSONB NOT NULL,
                max_concurrent INTEGER DEFAULT 1,
                current_load INTEGER DEFAULT 0
            )
        """)
        
        # Add indexes for queue performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_queue_stage_status 
            ON posts (queue_stage, queue_status)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_assigned_at 
            ON posts (assigned_at) WHERE assigned_at IS NOT NULL
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_queue_results_post_stage 
            ON queue_results (post_id, stage)
        """)
        
        conn.commit()
    conn.close()

@app.get("/health")
def health():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM posts")
            total_posts = cur.fetchone()[0]
        conn.close()
        return {"status": "healthy", "database": "connected", "total_posts": total_posts}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/posts")
def get_posts():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM posts ORDER BY created_utc DESC LIMIT 10")
        posts = cur.fetchall()
    conn.close()
    return {"posts": posts}

@app.post("/dummy-insert")
def dummy_insert():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO posts (reddit_id, title, author, url, body) 
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (reddit_id) DO NOTHING
        """, ("test123", "Test Post", "testuser", "http://example.com", "Test body"))
        conn.commit()
    conn.close()
    return {"message": "Test post inserted"}

@app.post("/scan")
def scan_subreddit(request: ScanRequest):
    try:
        reddit = get_reddit_client()
        
        # Test Reddit connection
        try:
            reddit.user.me()
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Reddit authentication failed: {str(e)}")
        
        # Calculate time threshold (posts within specified hours)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=request.hours)
        cutoff_timestamp = cutoff_time.timestamp()
        
        subreddit = reddit.subreddit(request.subreddit)
        
        found_posts = 0
        saved_posts = 0
        sample_posts = []
        
        # Scan new posts
        for submission in subreddit.new(limit=100):
            if submission.created_utc < cutoff_timestamp:
                continue
                
            found_posts += 1
            
            # Save to database
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO posts (reddit_id, title, author, created_utc, url, body, queue_stage, queue_status) 
                        VALUES (%s, %s, %s, %s, %s, %s, 'triage', 'pending')
                        ON CONFLICT (reddit_id) DO NOTHING
                        RETURNING id
                    """, (
                        submission.id,
                        submission.title,
                        str(submission.author) if submission.author else "[deleted]",
                        datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
                        submission.url,
                        submission.selftext if hasattr(submission, 'selftext') else ""
                    ))
                    
                    if cur.fetchone():
                        saved_posts += 1
                        
                    conn.commit()
            finally:
                conn.close()
            
            # Add to sample (first 5 posts)
            if len(sample_posts) < 5:
                sample_posts.append({
                    "id": submission.id,
                    "title": submission.title,
                    "author": str(submission.author) if submission.author else "[deleted]",
                    "created_utc": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
                    "url": submission.url
                })
        
        return {
            "subreddit": request.subreddit,
            "hours": request.hours,
            "found": found_posts,
            "saved": saved_posts,
            "sample": sample_posts
        }
        
    except Exception as e:
        if "401" in str(e):
            raise HTTPException(status_code=401, detail=str(e))
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")


# Queue Management API Endpoints

@app.get("/queue/status")
async def queue_status():
    """Get current queue processing status"""
    try:
        status = await get_queue_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue status: {str(e)}")


@app.get("/queue/stats")
async def queue_stats():
    """Get detailed queue statistics"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get detailed stats by stage and status
            cur.execute("""
                SELECT 
                    queue_stage,
                    queue_status,
                    COUNT(*) as count,
                    AVG(retry_count) as avg_retries,
                    MIN(created_utc) as oldest_post,
                    MAX(created_utc) as newest_post
                FROM posts 
                WHERE queue_stage IN ('triage', 'research', 'response', 'editorial', 'post_queue', 'completed', 'rejected')
                GROUP BY queue_stage, queue_status
                ORDER BY queue_stage, queue_status
            """)
            
            detailed_stats = []
            for row in cur.fetchall():
                detailed_stats.append({
                    "stage": row[0],
                    "status": row[1], 
                    "count": row[2],
                    "avg_retries": float(row[3]) if row[3] else 0,
                    "oldest_post": row[4].isoformat() if row[4] else None,
                    "newest_post": row[5].isoformat() if row[5] else None
                })
            
            # Get processing history
            cur.execute("""
                SELECT stage, COUNT(*) as total_processed
                FROM queue_results
                GROUP BY stage
                ORDER BY stage
            """)
            
            processing_history = {}
            for stage, count in cur.fetchall():
                processing_history[stage] = count
        
        conn.close()
        
        return {
            "detailed_stats": detailed_stats,
            "processing_history": processing_history,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue stats: {str(e)}")


@app.post("/queue/retry/{post_id}")
async def retry_post(post_id: int):
    """Manually retry a failed post"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Reset post to pending status
            cur.execute("""
                UPDATE posts 
                SET queue_status = 'pending',
                    assigned_to = NULL,
                    assigned_at = NULL,
                    retry_count = 0
                WHERE id = %s
                RETURNING queue_stage, queue_status
            """, (post_id,))
            
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Post not found")
            
            conn.commit()
        conn.close()
        
        return {
            "message": f"Post {post_id} reset to pending status",
            "stage": result[0],
            "status": result[1]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retry post: {str(e)}")


@app.get("/posts/{post_id}/history")
async def get_post_history(post_id: int):
    """Get complete processing history for a post"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get post details
            cur.execute("""
                SELECT id, reddit_id, title, author, created_utc, 
                       queue_stage, queue_status, retry_count, metadata
                FROM posts WHERE id = %s
            """, (post_id,))
            
            post_row = cur.fetchone()
            if not post_row:
                raise HTTPException(status_code=404, detail="Post not found")
            
            post_data = {
                "id": post_row[0],
                "reddit_id": post_row[1],
                "title": post_row[2],
                "author": post_row[3],
                "created_utc": post_row[4].isoformat() if post_row[4] else None,
                "current_stage": post_row[5],
                "current_status": post_row[6],
                "retry_count": post_row[7],
                "metadata": post_row[8]
            }
            
            # Get processing history
            cur.execute("""
                SELECT stage, result, created_at
                FROM queue_results
                WHERE post_id = %s
                ORDER BY created_at ASC
            """, (post_id,))
            
            history = []
            for stage, result_json, created_at in cur.fetchall():
                history.append({
                    "stage": stage,
                    "result": result_json,
                    "timestamp": created_at.isoformat()
                })
        
        conn.close()
        
        return {
            "post": post_data,
            "processing_history": history
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get post history: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5151)