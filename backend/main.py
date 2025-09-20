import os
import psycopg
import praw
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment variables from .env file
# Try both root level and parent directory for compatibility
load_dotenv(".env")  # For when running from project root
load_dotenv("../.env")  # For when running from backend directory

# Import queue management system
import sys
from pathlib import Path

# Add current directory to path for imports
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

from queue_management.queue_manager import start_queue_manager, stop_queue_manager, get_queue_status

async def setup_database_schema():
    """Setup database schema for queue management"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Add queue management columns to posts table
            print("Setting up database schema for queue management...")
            
            # Add queue columns if they don't exist
            cur.execute("""
                ALTER TABLE posts 
                ADD COLUMN IF NOT EXISTS queue_stage VARCHAR(50) DEFAULT 'triage',
                ADD COLUMN IF NOT EXISTS queue_status VARCHAR(50) DEFAULT 'pending',
                ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(100),
                ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
            """)
            
            # Create agent_prompts table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_prompts (
                    id SERIAL PRIMARY KEY,
                    agent_stage VARCHAR(50) NOT NULL,
                    system_prompt TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Create queue_state table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS queue_state (
                    id SERIAL PRIMARY KEY,
                    stage VARCHAR(50) UNIQUE NOT NULL,
                    is_paused BOOLEAN DEFAULT false,
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Create queue_results table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS queue_results (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER REFERENCES posts(id),
                    stage VARCHAR(50) NOT NULL,
                    content JSONB,
                    success BOOLEAN DEFAULT true,
                    error_message TEXT,
                    processing_time REAL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Create agent_config table for UI selections
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_config (
                    id SERIAL PRIMARY KEY,
                    agent_stage VARCHAR(50) UNIQUE NOT NULL,
                    model VARCHAR(100) NOT NULL,
                    endpoint VARCHAR(200) NOT NULL,
                    timeout INTEGER DEFAULT 120,
                    max_concurrent INTEGER DEFAULT 2,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Create queue_settings table for retry configuration
            cur.execute("""
                CREATE TABLE IF NOT EXISTS queue_settings (
                    id SERIAL PRIMARY KEY,
                    setting_key VARCHAR(100) UNIQUE NOT NULL,
                    setting_value TEXT NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)

            # Insert default retry settings
            cur.execute("""
                INSERT INTO queue_settings (setting_key, setting_value, description)
                VALUES
                    ('retry_timeout_seconds', '300', 'How long to wait before retrying failed posts (seconds)'),
                    ('max_retry_attempts', '3', 'Maximum number of retry attempts per post'),
                    ('stuck_post_threshold_minutes', '30', 'Minutes before a post is considered stuck')
                ON CONFLICT (setting_key) DO NOTHING;
            """)

            # Add retry tracking columns to posts table if they don't exist
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'retry_count') THEN
                        ALTER TABLE posts ADD COLUMN retry_count INTEGER DEFAULT 0;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'last_retry_at') THEN
                        ALTER TABLE posts ADD COLUMN last_retry_at TIMESTAMP;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'last_error_message') THEN
                        ALTER TABLE posts ADD COLUMN last_error_message TEXT;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'processing_started_at') THEN
                        ALTER TABLE posts ADD COLUMN processing_started_at TIMESTAMP;
                    END IF;
                END $$;
            """)
            
            # Initialize queue states if empty (preserve existing pause states)
            cur.execute("""
                INSERT INTO queue_state (stage, is_paused)
                VALUES ('triage', false), ('research', false), ('response', false), ('editorial', false)
                ON CONFLICT (stage) DO NOTHING;
            """)
            
        conn.commit()
        print("Database schema setup completed successfully")
    except Exception as e:
        print(f"Error setting up database schema: {e}")
        conn.rollback()
    finally:
        conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager"""
    # Startup
    print("Starting Reddit Claim Verifier with Queue Management...")
    await setup_database_schema()
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
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    username = os.getenv("REDDIT_USERNAME")
    password = os.getenv("REDDIT_PASSWORD")
    user_agent = os.getenv("REDDIT_USER_AGENT", "reddit-claim-verifier/1.0")
    
    # Debug: Log what credentials we're using (masked)
    print(f"🔐 Reddit Auth Debug:")
    print(f"   Client ID: {client_id[:5] + '...' + client_id[-3:] if client_id else 'NOT_SET'}")
    print(f"   Client Secret: {client_secret[:5] + '...' + client_secret[-3:] if client_secret and len(client_secret) > 8 else 'NOT_SET'}")
    print(f"   Username: {username if username else 'NOT_SET'}")
    print(f"   Password: {'*' * len(password) if password else 'NOT_SET'}")
    print(f"   User Agent: {user_agent}")
    
    if not all([client_id, client_secret, username, password]):
        print("❌ Missing Reddit credentials in environment variables")
        return None
    
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=user_agent
    )

def get_db_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5443"),
        dbname=os.getenv("DB_NAME", "redditmon"),
        user=os.getenv("DB_USER", "redditmon"),
        password=os.getenv("DB_PASSWORD", "supersecret")
    )

# Removed deprecated @app.on_event("startup") - database setup now handled in lifespan

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

@app.post("/scan")
def scan_subreddit(request: ScanRequest):
    try:
        reddit = get_reddit_client()
        
        if reddit is None:
            raise HTTPException(status_code=500, detail="Reddit client could not be created - check environment variables")
        
        # Test Reddit connection
        try:
            user = reddit.user.me()
            print(f"✅ Successfully authenticated as u/{user.name}")
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Reddit authentication failed: {error_msg}")
            
            # Provide specific error messages for common issues
            if "401" in error_msg or "Unauthorized" in error_msg:
                if "may be restricted" in error_msg.lower() or "suspended" in error_msg.lower():
                    detail = "Reddit authentication failed: Account may be restricted or suspended. Check your Reddit account status."
                else:
                    detail = "Reddit authentication failed: Invalid credentials. Check your Client ID, Client Secret, username, and password in .env file."
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                detail = "Reddit authentication failed: Rate limited. Try again in a few minutes."
            else:
                detail = f"Reddit authentication failed: {error_msg}"
                
            raise HTTPException(status_code=401, detail=detail)
        
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
            
            # Collect comprehensive post text
            post_body = ""
            
            # Get main post text
            if hasattr(submission, 'selftext') and submission.selftext:
                post_body += f"Post Content:\n{submission.selftext}\n\n"
            
            # Get top comments for context (limit to avoid too much data)
            try:
                submission.comments.replace_more(limit=0)  # Remove "load more comments"
                top_comments = []
                for comment in submission.comments.list()[:10]:  # Top 10 comments
                    if hasattr(comment, 'body') and comment.body != '[deleted]':
                        author = str(comment.author) if comment.author else "[deleted]"
                        top_comments.append(f"Comment by u/{author}: {comment.body}")
                
                if top_comments:
                    post_body += "Top Comments:\n" + "\n".join(top_comments) + "\n\n"
                    
            except Exception as e:
                print(f"Could not fetch comments for {submission.id}: {e}")
            
            # For link posts, note the URL
            if submission.url != submission.permalink:
                post_body += f"External Link: {submission.url}\n\n"
            
            # Add post metadata for context
            post_body += f"Post Metadata:\n"
            post_body += f"Score: {submission.score}\n"
            post_body += f"Upvote ratio: {getattr(submission, 'upvote_ratio', 'N/A')}\n"
            post_body += f"Number of comments: {submission.num_comments}\n"
            post_body += f"Post type: {'Self post' if submission.is_self else 'Link post'}\n"
            
            # Truncate if too long (keep within reasonable limits)
            if len(post_body) > 10000:
                post_body = post_body[:10000] + "\n\n[Content truncated...]"
            
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
                        post_body
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


@app.get("/queue/pending/{stage}")
async def get_pending_posts(stage: str):
    """Get detailed list of pending posts for a specific stage"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get pending posts with titles and metadata for the specified stage
            cur.execute("""
                SELECT
                    id,
                    reddit_id,
                    title,
                    author,
                    created_utc,
                    retry_count,
                    processing_started_at,
                    last_retry_at
                FROM posts
                WHERE queue_stage = %s AND queue_status = 'pending'
                ORDER BY created_utc ASC
            """, (stage,))

            pending_posts = []
            for row in cur.fetchall():
                pending_posts.append({
                    "id": row[0],
                    "reddit_id": row[1],
                    "title": row[2],
                    "author": row[3],
                    "created_utc": row[4].isoformat() if row[4] else None,
                    "retry_count": row[5],
                    "processing_started_at": row[6].isoformat() if row[6] else None,
                    "last_retry_at": row[7].isoformat() if row[7] else None
                })

        conn.close()
        return {
            "stage": stage,
            "pending_posts": pending_posts,
            "count": len(pending_posts),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pending posts: {str(e)}")


@app.get("/queue/post-results/{post_id}")
async def get_post_results(post_id: int):
    """Get all stage results for a specific post"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get post info
            cur.execute("""
                SELECT id, title, queue_stage, queue_status
                FROM posts
                WHERE id = %s
            """, (post_id,))

            post_info = cur.fetchone()
            if not post_info:
                raise HTTPException(status_code=404, detail=f"Post {post_id} not found")

            # Get all queue results for this post, ordered by stage progression
            cur.execute("""
                SELECT stage, content, created_at
                FROM queue_results
                WHERE post_id = %s
                ORDER BY
                    CASE stage
                        WHEN 'triage' THEN 1
                        WHEN 'research' THEN 2
                        WHEN 'response' THEN 3
                        WHEN 'editorial' THEN 4
                        ELSE 5
                    END,
                    created_at ASC
            """, (post_id,))

            results = cur.fetchall()

        conn.close()

        # Format the results
        stage_results = {}
        for result in results:
            stage, content, created_at = result
            stage_results[stage] = {
                "content": content,
                "created_at": created_at.isoformat()
            }

        return {
            "post_id": post_info[0],
            "title": post_info[1],
            "current_stage": post_info[2],
            "queue_status": post_info[3],
            "stage_results": stage_results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get post results: {str(e)}")


@app.get("/queue/rejected")
async def get_rejected_posts():
    """Get all posts that were rejected during triage with their rejection reasoning"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get rejected posts with their triage results
            cur.execute("""
                SELECT
                    p.id,
                    p.title,
                    p.author,
                    p.url,
                    p.body,
                    p.created_utc,
                    p.inserted_at,
                    qr.content as triage_result
                FROM posts p
                LEFT JOIN queue_results qr ON p.id = qr.post_id AND qr.stage = 'triage'
                WHERE p.queue_stage = 'rejected' AND p.queue_status = 'rejected'
                ORDER BY p.inserted_at DESC
            """)

            rejected_posts = []
            for row in cur.fetchall():
                post_id, title, author, url, body, created_utc, inserted_at, triage_result = row

                # Extract rejection reasoning from triage result
                rejection_reasoning = "No reasoning available"
                if triage_result and isinstance(triage_result, dict):
                    content = triage_result.get('content', {})
                    if isinstance(content, dict):
                        rejection_reasoning = content.get('reasoning', 'No reasoning available')

                rejected_posts.append({
                    "id": post_id,
                    "title": title,
                    "author": author,
                    "url": url,
                    "body": body,
                    "created_utc": created_utc.isoformat() if created_utc else None,
                    "inserted_at": inserted_at.isoformat() if inserted_at else None,
                    "rejection_reasoning": rejection_reasoning,
                    "triage_result": triage_result
                })

        conn.close()

        return {
            "rejected_posts": rejected_posts,
            "total_count": len(rejected_posts),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get rejected posts: {str(e)}")


@app.post("/queue/pause/{stage}")
async def pause_queue(stage: str):
    """Pause processing for a specific queue stage"""
    print(f"🛑 Pausing queue stage: {stage}")
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO queue_state (stage, is_paused, updated_at)
                VALUES (%s, TRUE, NOW())
                ON CONFLICT (stage) DO UPDATE SET
                    is_paused = TRUE,
                    updated_at = NOW()
                RETURNING stage, is_paused
            """, (stage,))

            result = cur.fetchone()
            conn.commit()
        conn.close()

        print(f"✅ Queue stage '{stage}' successfully paused")
        return {
            "stage": result[0],
            "is_paused": result[1],
            "message": f"Queue stage '{stage}' has been paused"
        }

    except Exception as e:
        print(f"❌ Failed to pause queue stage '{stage}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to pause queue: {str(e)}")


@app.post("/queue/resume/{stage}")
async def resume_queue(stage: str):
    """Resume processing for a specific queue stage"""
    print(f"▶️ Resuming queue stage: {stage}")
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO queue_state (stage, is_paused, updated_at)
                VALUES (%s, FALSE, NOW())
                ON CONFLICT (stage) DO UPDATE SET
                    is_paused = FALSE,
                    updated_at = NOW()
                RETURNING stage, is_paused
            """, (stage,))

            result = cur.fetchone()
            conn.commit()
        conn.close()

        print(f"✅ Queue stage '{stage}' successfully resumed")
        return {
            "stage": result[0],
            "is_paused": result[1],
            "message": f"Queue stage '{stage}' has been resumed"
        }

    except Exception as e:
        print(f"❌ Failed to resume queue stage '{stage}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to resume queue: {str(e)}")


@app.post("/queue/reload-agents")
async def reload_agent_configurations():
    """Reload agent configurations from database"""
    try:
        from queue_management.queue_manager import queue_manager

        print("🔄 Reloading agent configurations from database...")

        # Re-initialize agents with database configurations
        queue_manager._initialize_agents()

        print("✅ Agent configurations reloaded successfully")

        return {
            "success": True,
            "message": "Agent configurations reloaded from database successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload agent configurations: {str(e)}")


@app.get("/queue/stuck-posts")
async def detect_stuck_posts():
    """Detect posts that have been stuck in processing for too long"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get stuck post threshold from settings
            cur.execute("SELECT setting_value FROM queue_settings WHERE setting_key = 'stuck_post_threshold_minutes'")
            threshold_result = cur.fetchone()
            threshold_minutes = int(threshold_result[0]) if threshold_result else 30

            # Find stuck posts - processing for longer than threshold or failed with retries available
            cur.execute("""
                SELECT id, reddit_id, title, queue_stage, queue_status,
                       retry_count, last_error_message, processing_started_at,
                       EXTRACT(EPOCH FROM (NOW() - processing_started_at))/60 as minutes_stuck
                FROM posts
                WHERE
                    (queue_status = 'processing' AND processing_started_at IS NOT NULL
                     AND processing_started_at < NOW() - INTERVAL '%s minutes')
                    OR
                    (queue_status = 'failed' AND retry_count < (
                        SELECT CAST(setting_value AS INTEGER) FROM queue_settings
                        WHERE setting_key = 'max_retry_attempts'
                    ))
                ORDER BY processing_started_at ASC NULLS LAST
            """, (threshold_minutes,))

            stuck_posts = []
            for row in cur.fetchall():
                stuck_posts.append({
                    "id": row[0],
                    "reddit_id": row[1],
                    "title": row[2],
                    "queue_stage": row[3],
                    "queue_status": row[4],
                    "retry_count": row[5],
                    "last_error_message": row[6],
                    "processing_started_at": row[7].isoformat() if row[7] else None,
                    "minutes_stuck": float(row[8]) if row[8] else None
                })

            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"🔍 [{timestamp}] Detected {len(stuck_posts)} stuck posts (threshold: {threshold_minutes} min)")
            for post in stuck_posts:
                print(f"   📋 Post {post['id']}: {post['queue_status']} retries: {post['retry_count']}")

            return {
                "success": True,
                "stuck_posts": stuck_posts,
                "threshold_minutes": threshold_minutes,
                "total_stuck": len(stuck_posts)
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detect stuck posts: {str(e)}")


@app.post("/queue/reset-stuck-posts")
async def reset_stuck_posts():
    """Reset stuck posts back to pending status for retry"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get stuck post threshold from settings (same as detect)
            cur.execute("SELECT setting_value FROM queue_settings WHERE setting_key = 'stuck_post_threshold_minutes'")
            threshold_result = cur.fetchone()
            threshold_minutes = int(threshold_result[0]) if threshold_result else 30

            # Get retry settings
            cur.execute("SELECT setting_value FROM queue_settings WHERE setting_key = 'max_retry_attempts'")
            max_retries_result = cur.fetchone()
            max_retries = int(max_retries_result[0]) if max_retries_result else 3

            # Reset stuck/failed posts that haven't exceeded retry limit (use same logic as detect)
            # Don't set last_retry_at for manual resets - they should be immediately available
            cur.execute("""
                UPDATE posts
                SET
                    queue_status = 'pending',
                    processing_started_at = NULL,
                    last_retry_at = NULL,
                    retry_count = retry_count + 1
                WHERE
                    (queue_status = 'processing' AND processing_started_at IS NOT NULL
                     AND processing_started_at < NOW() - INTERVAL '%s minutes')
                    OR
                    (queue_status = 'failed' AND retry_count < %s)
                RETURNING id, reddit_id, queue_stage, retry_count
            """, (threshold_minutes, max_retries))

            reset_posts = []
            for row in cur.fetchall():
                reset_posts.append({
                    "id": row[0],
                    "reddit_id": row[1],
                    "queue_stage": row[2],
                    "retry_count": row[3]
                })

            conn.commit()

            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"🔄 [{timestamp}] Reset {len(reset_posts)} stuck posts for retry (threshold: {threshold_minutes} min, max_retries: {max_retries})")
            for post in reset_posts:
                print(f"   📝 Post {post['id']}: {post['reddit_id']} -> retry #{post['retry_count']}")

            return {
                "success": True,
                "reset_posts": reset_posts,
                "total_reset": len(reset_posts)
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset stuck posts: {str(e)}")


@app.get("/queue/settings")
async def get_queue_settings():
    """Get queue retry settings"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT setting_key, setting_value, description FROM queue_settings ORDER BY setting_key")

            settings = {}
            for row in cur.fetchall():
                settings[row[0]] = {
                    "value": row[1],
                    "description": row[2]
                }

            return {
                "success": True,
                "settings": settings
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue settings: {str(e)}")


class QueueSettingUpdate(BaseModel):
    setting_key: str
    setting_value: str

@app.post("/queue/settings")
async def update_queue_setting(setting: QueueSettingUpdate):
    """Update a queue retry setting"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE queue_settings
                SET setting_value = %s, updated_at = NOW()
                WHERE setting_key = %s
                RETURNING setting_key, setting_value
            """, (setting.setting_value, setting.setting_key))

            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"Setting '{setting.setting_key}' not found")

            conn.commit()

            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"⚙️ [{timestamp}] Updated queue setting: {setting.setting_key} = {setting.setting_value}")

            return {
                "success": True,
                "setting_key": result[0],
                "setting_value": result[1]
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update queue setting: {str(e)}")


# Agent System Prompt Management

class SystemPromptUpdate(BaseModel):
    agent_stage: str
    system_prompt: str

@app.get("/agents/prompts")
async def get_agent_prompts():
    """Get all agent system prompts"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT agent_stage, system_prompt, version, updated_at
                FROM agent_prompts
                ORDER BY agent_stage
            """)
            
            prompts = []
            for row in cur.fetchall():
                prompts.append({
                    "agent_stage": row[0],
                    "system_prompt": row[1],
                    "version": row[2],
                    "updated_at": row[3].isoformat() if row[3] else None
                })
        conn.close()
        
        return {"prompts": prompts}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agent prompts: {str(e)}")


@app.post("/agents/prompts")
async def update_agent_prompt(prompt_data: SystemPromptUpdate):
    """Update system prompt for a specific agent"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Check if prompt exists
            cur.execute("""
                SELECT version FROM agent_prompts WHERE agent_stage = %s
            """, (prompt_data.agent_stage,))
            
            result = cur.fetchone()
            current_version = result[0] if result else 0
            
            # Insert or update prompt
            cur.execute("""
                INSERT INTO agent_prompts (agent_stage, system_prompt, version, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (agent_stage) DO UPDATE SET 
                    system_prompt = EXCLUDED.system_prompt,
                    version = agent_prompts.version + 1,
                    updated_at = NOW()
                RETURNING agent_stage, version
            """, (prompt_data.agent_stage, prompt_data.system_prompt, current_version + 1))
            
            result = cur.fetchone()
            conn.commit()
        conn.close()
        
        return {
            "agent_stage": result[0],
            "version": result[1],
            "message": f"System prompt updated for {result[0]} agent"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update agent prompt: {str(e)}")


@app.post("/agents/prompts/sync")
async def sync_agent_prompts():
    """Sync database agent_prompts with latest default prompts from agent classes"""
    try:
        from agents.triage_agent import TriageAgent
        from agents.research_agent import ResearchAgent
        from agents.response_agent import ResponseAgent
        from agents.editorial_agent import EditorialAgent
        
        agents = {
            'triage': TriageAgent("sync-model", "http://localhost:11434"),
            'research': ResearchAgent("sync-model", "http://localhost:11434"),
            'response': ResponseAgent("sync-model", "http://localhost:11434"),
            'editorial': EditorialAgent("sync-model", "http://localhost:11434")
        }
        
        conn = get_db_connection()
        synced_agents = []
        
        with conn.cursor() as cur:
            for stage, agent in agents.items():
                # Get the latest default prompt from the agent class
                latest_prompt = agent.get_default_system_prompt()
                
                # Check if this prompt already exists in database
                cur.execute("""
                    SELECT system_prompt, version FROM agent_prompts 
                    WHERE agent_stage = %s 
                    ORDER BY version DESC LIMIT 1
                """, (stage,))
                
                result = cur.fetchone()
                current_prompt = result[0] if result else None
                current_version = result[1] if result else 0
                
                if current_prompt != latest_prompt:
                    # Update database with latest prompt
                    new_version = current_version + 1
                    cur.execute("""
                        INSERT INTO agent_prompts (agent_stage, system_prompt, version, is_active, updated_at)
                        VALUES (%s, %s, %s, true, NOW())
                        ON CONFLICT (agent_stage) DO UPDATE SET 
                            system_prompt = EXCLUDED.system_prompt,
                            version = agent_prompts.version + 1,
                            updated_at = NOW(),
                            is_active = true
                    """, (stage, latest_prompt, new_version))
                    
                    synced_agents.append({
                        "stage": stage,
                        "old_version": current_version,
                        "new_version": new_version,
                        "has_time_instructions": "CRITICAL INSTRUCTION" in latest_prompt
                    })
                    
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": f"Synced {len(synced_agents)} agent prompts with latest defaults",
            "synced_agents": synced_agents,
            "total_agents": len(agents)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync agent prompts: {str(e)}")


@app.get("/agents/config")
async def get_agent_config():
    """Get configuration for all agents from database with fallback to defaults"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT agent_stage, model, endpoint, timeout, max_concurrent FROM agent_config")
            rows = cur.fetchall()
            
            # Convert to dict with agent_stage as key
            db_config = {}
            for row in rows:
                stage, model, endpoint, timeout, max_concurrent = row
                db_config[stage] = {
                    "model": model,
                    "endpoint": endpoint,
                    "timeout": timeout,
                    "max_concurrent": max_concurrent
                }
            
            # Always load defaults and merge with database values
            from agents.agent_config import AGENT_CONFIG
            merged_config = {}
            for stage, config in AGENT_CONFIG.items():
                # Use database config if available, otherwise use defaults
                if stage in db_config:
                    merged_config[stage] = db_config[stage]
                else:
                    merged_config[stage] = {
                        "model": config["model"],
                        "endpoint": config["endpoint"],
                        "timeout": config["timeout"],
                        "max_concurrent": config["max_concurrent"]
                    }
            
            return {"config": merged_config}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agent config: {str(e)}")


class AgentConfigUpdate(BaseModel):
    agent_stage: str
    model: str
    endpoint: str
    timeout: int = 120
    max_concurrent: int = 2


@app.post("/agents/config")
async def save_agent_config(config_update: AgentConfigUpdate):
    """Save agent configuration to database"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO agent_config (agent_stage, model, endpoint, timeout, max_concurrent, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (agent_stage)
                DO UPDATE SET
                    model = EXCLUDED.model,
                    endpoint = EXCLUDED.endpoint,
                    timeout = EXCLUDED.timeout,
                    max_concurrent = EXCLUDED.max_concurrent,
                    updated_at = NOW()
            """, (
                config_update.agent_stage,
                config_update.model, 
                config_update.endpoint,
                config_update.timeout,
                config_update.max_concurrent
            ))
        conn.commit()
        return {"success": True, "message": f"Agent config for {config_update.agent_stage} saved successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save agent config: {str(e)}")


# Pydantic models
class CredentialsUpdate(BaseModel):
    reddit_client_id: str
    reddit_client_secret: str
    reddit_username: str
    reddit_password: str
    reddit_user_agent: str = "reddit-claim-verifier/1.0"


@app.post("/update-credentials")
def update_credentials(credentials: CredentialsUpdate):
    try:
        # Read current .env file - detect native vs Docker environment
        if os.path.exists("/app/.env"):
            env_path = "/app/.env"  # Docker environment
        else:
            env_path = "../.env"    # Native development (relative to backend directory)
        env_lines = []
        
        # Read existing .env file
        try:
            with open(env_path, 'r') as f:
                env_lines = f.readlines()
        except FileNotFoundError:
            # Create basic .env structure if it doesn't exist
            env_lines = [
                "# Database Configuration\n",
                "DB_HOST=db\n",
                "DB_PORT=5443\n", 
                "DB_NAME=redditmon\n",
                "DB_USER=redditmon\n",
                "DB_PASSWORD=supersecret\n",
                "\n",
                "# Reddit API Credentials\n",
            ]
        
        # Update Reddit credentials in .env file
        updated_lines = []
        reddit_keys = {
            'REDDIT_CLIENT_ID': credentials.reddit_client_id,
            'REDDIT_CLIENT_SECRET': credentials.reddit_client_secret,
            'REDDIT_USERNAME': credentials.reddit_username,
            'REDDIT_PASSWORD': credentials.reddit_password,
            'REDDIT_USER_AGENT': credentials.reddit_user_agent
        }
        
        # Track which credentials we've updated
        updated_keys = set()
        
        for line in env_lines:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key = line.split('=')[0]
                if key in reddit_keys:
                    updated_lines.append(f"{key}={reddit_keys[key]}\n")
                    updated_keys.add(key)
                else:
                    updated_lines.append(line + '\n')
            else:
                updated_lines.append(line + '\n')
        
        # Add any missing Reddit credentials
        for key, value in reddit_keys.items():
            if key not in updated_keys:
                updated_lines.append(f"{key}={value}\n")
        
        # Write updated .env file
        with open(env_path, 'w') as f:
            f.writelines(updated_lines)
        
        return {
            "message": "Credentials updated successfully. Backend restart required to take effect.",
            "restart_required": True
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update credentials: {str(e)}")

@app.post("/restart-backend")
def restart_backend():
    """Note: Manual restart required - Docker Compose doesn't auto-restart on SIGTERM"""
    return {
        "message": "Credentials updated. Please refresh the page in a few seconds - backend will reload environment variables.",
        "note": "Docker restart is handled externally"
    }

# LLM Endpoint Proxy (to bypass CORS)
class TestEndpointRequest(BaseModel):
    endpoint_url: str

@app.post("/test-llm-endpoint")
async def test_llm_endpoint(request: TestEndpointRequest):
    """Proxy endpoint to test LLM endpoints and fetch available models (bypasses CORS)"""
    try:
        import requests
        import re
        
        # Ensure the URL has the correct format
        endpoint_url = request.endpoint_url.rstrip('/')
        
        # Native mode: Use endpoints as-is (no Docker translation needed)
        print(f"🔍 Native mode - using endpoint as-is: {endpoint_url}")
        
        models_url = f"{endpoint_url}/v1/models"
        
        print(f"🔍 Testing LLM endpoint: {models_url}")
        
        # Make request to the LLM endpoint
        response = requests.get(models_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'data' in data and isinstance(data['data'], list):
                models = [model.get('id', 'unknown') for model in data['data']]
                print(f"✅ Found {len(models)} models: {models}")
                
                return {
                    "success": True,
                    "models": models,
                    "endpoint": endpoint_url,
                    "model_count": len(models)
                }
            else:
                raise Exception("Invalid response format - missing 'data' array")
                
        else:
            raise Exception(f"HTTP {response.status_code}: {response.text}")
            
    except requests.exceptions.ConnectTimeout:
        raise HTTPException(status_code=408, detail="Connection timeout - endpoint may be unreachable")
    except requests.exceptions.ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Connection failed: {str(e)}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Endpoint test failed: {str(e)}")


@app.get("/posts/completed-editorial")
async def get_completed_editorial_posts():
    """Get posts that have completed the editorial stage and are ready for human review"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get posts that completed editorial stage or are in post_queue
            cur.execute("""
                SELECT
                    p.id,
                    p.reddit_id,
                    p.title,
                    p.author,
                    p.url,
                    p.body,
                    p.created_utc,
                    p.queue_stage,
                    p.queue_status
                FROM posts p
                WHERE (p.queue_stage = 'editorial' AND p.queue_status = 'completed')
                   OR (p.queue_stage = 'post_queue' AND p.queue_status = 'pending')
                ORDER BY p.created_utc DESC
                LIMIT 50
            """)

            completed_posts = []
            for row in cur.fetchall():
                completed_posts.append({
                    "id": row[0],
                    "reddit_id": row[1],
                    "title": row[2],
                    "author": row[3],
                    "url": row[4],
                    "body": row[5],
                    "created_utc": row[6].isoformat() if row[6] else None,
                    "queue_stage": row[7],
                    "queue_status": row[8]
                })

        conn.close()
        return {
            "posts": completed_posts,
            "count": len(completed_posts),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get completed editorial posts: {str(e)}")


@app.post("/posts/submit-to-reddit")
async def submit_to_reddit(request: dict):
    """Submit a response to Reddit using PRAW"""
    try:
        post_id = request.get('post_id')
        reddit_id = request.get('reddit_id')
        response_content = request.get('response_content')

        if not all([post_id, reddit_id, response_content]):
            raise HTTPException(status_code=400, detail="Missing required fields: post_id, reddit_id, response_content")

        # Import PRAW here to avoid import errors if not installed
        try:
            import praw
        except ImportError:
            raise HTTPException(status_code=500, detail="PRAW library not installed. Please install with: pip install praw")

        # Get Reddit credentials from environment
        import os
        reddit_client_id = os.getenv('REDDIT_CLIENT_ID')
        reddit_client_secret = os.getenv('REDDIT_CLIENT_SECRET')
        reddit_username = os.getenv('REDDIT_USERNAME')
        reddit_password = os.getenv('REDDIT_PASSWORD')
        reddit_user_agent = os.getenv('REDDIT_USER_AGENT', f'RedditMonitor/1.0 by {reddit_username}')

        if not all([reddit_client_id, reddit_client_secret, reddit_username, reddit_password]):
            raise HTTPException(status_code=500, detail="Reddit credentials not configured. Please set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, and REDDIT_PASSWORD environment variables.")

        # Initialize Reddit instance
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            username=reddit_username,
            password=reddit_password,
            user_agent=reddit_user_agent
        )

        # Get the submission by ID and reply to it
        submission = reddit.submission(id=reddit_id)
        comment = submission.reply(response_content)

        # Update the post status in database
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE posts
                SET queue_stage = 'post_queue', queue_status = 'completed'
                WHERE id = %s
            """, (post_id,))

            # Log the successful posting
            cur.execute("""
                INSERT INTO queue_results (post_id, stage, content, success, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                post_id,
                'reddit_post',
                {"comment_id": comment.id, "permalink": comment.permalink, "response": response_content},
                True,
                datetime.now(timezone.utc)
            ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "comment_id": comment.id,
            "permalink": comment.permalink,
            "message": "Successfully posted to Reddit"
        }

    except Exception as e:
        # Log the error
        if 'post_id' in locals():
            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO queue_results (post_id, stage, content, success, error_message, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        post_id,
                        'reddit_post',
                        {"error": str(e)},
                        False,
                        str(e),
                        datetime.now(timezone.utc)
                    ))
                conn.commit()
                conn.close()
            except:
                pass  # Don't fail if we can't log the error

        raise HTTPException(status_code=500, detail=f"Failed to post to Reddit: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5151)