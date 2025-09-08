#!/usr/bin/env python3
"""
Test Reddit authentication with your credentials
"""
import os
import sys
from pathlib import Path

# Load environment from .env file
def load_env_file(filepath):
    """Simple .env file loader"""
    if Path(filepath).exists():
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key and value and key not in os.environ:
                        os.environ[key] = value

# Load environment
load_env_file('.env')

# Add backend to path
sys.path.append('./backend')

try:
    import praw
    
    print("Testing Reddit Authentication...")
    print("=" * 40)
    
    # Get credentials from environment
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    username = os.getenv("REDDIT_USERNAME")
    password = os.getenv("REDDIT_PASSWORD")
    user_agent = os.getenv("REDDIT_USER_AGENT", "reddit-claim-verifier/1.0")
    
    # Check if credentials are set
    if not client_id or client_id == "your_reddit_client_id":
        print("❌ REDDIT_CLIENT_ID not set in .env file")
        sys.exit(1)
        
    if not client_secret or client_secret == "your_reddit_client_secret":
        print("❌ REDDIT_CLIENT_SECRET not set in .env file")
        sys.exit(1)
        
    if not username or username == "your_reddit_username":
        print("❌ REDDIT_USERNAME not set in .env file")
        sys.exit(1)
        
    if not password or password == "your_reddit_password":
        print("❌ REDDIT_PASSWORD not set in .env file")
        sys.exit(1)
    
    print(f"✓ Client ID: {client_id[:5]}...{client_id[-3:]}")
    print(f"✓ Client Secret: {client_secret[:5]}...{client_secret[-3:]}")
    print(f"✓ Username: {username}")
    print(f"✓ User Agent: {user_agent}")
    print()
    
    # Create Reddit instance
    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=user_agent
    )
    
    # Test authentication
    print("Testing authentication...")
    try:
        user = reddit.user.me()
        print(f"✅ Authentication successful!")
        print(f"   Logged in as: u/{user.name}")
        print(f"   Account created: {user.created_utc}")
        print(f"   Link karma: {user.link_karma}")
        print(f"   Comment karma: {user.comment_karma}")
        
        # Test subreddit access
        print("\nTesting subreddit access...")
        subreddit = reddit.subreddit("test")
        print(f"✅ Can access r/{subreddit.display_name}")
        print(f"   Subscribers: {subreddit.subscribers:,}")
        
        print("\n🎉 Reddit authentication is working perfectly!")
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        print("\nPossible issues:")
        print("1. Check your Reddit app credentials at https://www.reddit.com/prefs/apps")
        print("2. Make sure you selected 'script' as the app type")
        print("3. Verify your username and password are correct")
        print("4. Check if your Reddit account has 2FA enabled (may need app password)")
        sys.exit(1)
        
except ImportError:
    print("❌ praw not installed. Run: pip install praw")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)