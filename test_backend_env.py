#!/usr/bin/env python3
"""
Test that the backend can load environment variables and create Reddit client
"""
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append('./backend')

# Load environment variables from .env file manually
def load_env_file():
    """Load environment variables from .env file"""
    env_path = Path('.env')
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key and value and key not in os.environ:
                        os.environ[key] = value
        print(f"✓ Loaded environment from {env_path}")
    else:
        print(f"⚠️  No .env file found at {env_path}")

# Load environment
load_env_file()

# Test Reddit client creation
try:
    import praw
    
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    username = os.getenv("REDDIT_USERNAME")
    password = os.getenv("REDDIT_PASSWORD")
    user_agent = os.getenv("REDDIT_USER_AGENT", "reddit-claim-verifier/1.0")
    
    print(f"🔐 Reddit Credentials Loaded:")
    print(f"   Client ID: {client_id[:5] + '...' + client_id[-3:] if client_id else 'NOT_SET'}")
    print(f"   Client Secret: {client_secret[:5] + '...' + client_secret[-3:] if client_secret and len(client_secret) > 8 else 'NOT_SET'}")
    print(f"   Username: {username if username else 'NOT_SET'}")
    print(f"   Password: {'*' * len(password) if password else 'NOT_SET'}")
    print(f"   User Agent: {user_agent}")
    
    if not all([client_id, client_secret, username, password]):
        print("❌ Missing Reddit credentials")
        sys.exit(1)
    
    # Create Reddit client
    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=user_agent
    )
    
    print("\n🔍 Testing Reddit Authentication...")
    
    # Test authentication
    try:
        user = reddit.user.me()
        print(f"✅ Successfully authenticated as u/{user.name}")
        print(f"   Account created: {user.created_utc}")
        print(f"   Link karma: {user.link_karma}")
        print(f"   Comment karma: {user.comment_karma}")
        
        # Test if account has any restrictions
        print(f"   Account suspended: {getattr(user, 'is_suspended', False)}")
        
        print("\n🎉 Backend environment loading works correctly!")
        print("   You can now start the FastAPI server and test the scan endpoint.")
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Reddit authentication failed: {error_msg}")
        
        if "401" in error_msg or "Unauthorized" in error_msg:
            print("\n🔍 This indicates:")
            print("   • Account may be restricted or suspended")
            print("   • Invalid credentials")
            print("   • Need to use app password if 2FA enabled")
        elif "403" in error_msg or "Forbidden" in error_msg:
            print("\n🔍 This indicates:")
            print("   • Account is suspended or restricted")
            print("   • App permissions issue")
        
        print("\n💡 Solutions:")
        print("   1. Check your Reddit account status by logging in manually")
        print("   2. Verify app credentials at https://www.reddit.com/prefs/apps") 
        print("   3. If you have 2FA, generate an app password")
        print("   4. Wait if you've been rate limited recently")
        
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("   Run: pip install praw")
except Exception as e:
    print(f"❌ Unexpected error: {e}")