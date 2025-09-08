import os
import psycopg
import praw
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

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
            
            # Initialize queue states if empty
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
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "redditmon"),
        user=os.getenv("DB_USER", "redditmon"),
        password=os.getenv("DB_PASSWORD", "supersecret")
    )

@app.on_event("startup")
def startup():
    # Create tables with queue management columns
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
        
        # Agent system prompts management table  
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_prompts (
                id SERIAL PRIMARY KEY,
                agent_stage VARCHAR(20) UNIQUE NOT NULL,
                system_prompt TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Queue state management table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS queue_state (
                id SERIAL PRIMARY KEY,
                stage VARCHAR(20) UNIQUE NOT NULL,
                is_paused BOOLEAN DEFAULT FALSE,
                max_concurrent INTEGER DEFAULT 1,
                poll_interval INTEGER DEFAULT 30,
                updated_at TIMESTAMPTZ DEFAULT NOW()
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


@app.post("/queue/pause/{stage}")
async def pause_queue(stage: str):
    """Pause processing for a specific queue stage"""
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
        
        return {
            "stage": result[0],
            "is_paused": result[1],
            "message": f"Queue stage '{stage}' has been paused"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause queue: {str(e)}")


@app.post("/queue/resume/{stage}")
async def resume_queue(stage: str):
    """Resume processing for a specific queue stage"""
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
        
        return {
            "stage": result[0],
            "is_paused": result[1],
            "message": f"Queue stage '{stage}' has been resumed"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume queue: {str(e)}")


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


@app.get("/agents/config")
async def get_agent_config():
    """Get configuration for all agents"""
    try:
        # Import here to avoid circular imports
        from agents.agent_config import AGENT_CONFIG, get_agent_summary
        
        summary = get_agent_summary()
        return {
            "config": AGENT_CONFIG,
            "summary": summary
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agent config: {str(e)}")


# Pydantic model for credentials update
class CredentialsUpdate(BaseModel):
    reddit_client_id: str
    reddit_client_secret: str
    reddit_username: str
    reddit_password: str
    reddit_user_agent: str = "reddit-claim-verifier/1.0"

@app.post("/update-credentials")
def update_credentials(credentials: CredentialsUpdate):
    try:
        # Read current .env file
        env_path = "/app/.env"  # Mounted .env file
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
                "DB_PORT=5432\n", 
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5151)