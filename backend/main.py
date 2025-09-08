import os
import psycopg
import praw
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Reddit Claim Verifier", version="1.0.0")

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
    # Create tables
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                reddit_id TEXT UNIQUE NOT NULL,
                title TEXT,
                author TEXT,
                created_utc TIMESTAMPTZ,
                url TEXT,
                body TEXT,
                inserted_at TIMESTAMPTZ DEFAULT NOW()
            )
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
            
            # Save to database
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO posts (reddit_id, title, author, created_utc, url, body) 
                        VALUES (%s, %s, %s, %s, %s, %s)
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