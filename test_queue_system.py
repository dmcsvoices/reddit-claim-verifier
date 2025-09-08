#!/usr/bin/env python3
"""
Test script for the Queue Management System
Tests the core functionality without requiring LLM endpoints
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

# Add backend to path for imports
sys.path.append('./backend')

# Load environment from .env.development if exists
from pathlib import Path

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

# Load development environment
load_env_file('.env.development')

# Set testing overrides
os.environ["USE_MOCK_AGENTS"] = "true"
if not os.environ.get("DB_HOST"):
    os.environ["DB_HOST"] = "localhost"
if not os.environ.get("DB_PORT"):
    os.environ["DB_PORT"] = "5443"  # Docker mapped port
if not os.environ.get("DB_NAME"):
    os.environ["DB_NAME"] = "redditmon"
if not os.environ.get("DB_USER"):
    os.environ["DB_USER"] = "redditmon"
if not os.environ.get("DB_PASSWORD"):
    os.environ["DB_PASSWORD"] = "supersecret"


async def test_database_setup():
    """Test database connection and setup"""
    print("Testing database setup...")
    
    try:
        from backend.main import get_db_connection
        
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Test basic connection
            cur.execute("SELECT COUNT(*) FROM posts")
            post_count = cur.fetchone()[0]
            print(f"✓ Database connected, {post_count} posts exist")
            
            # Test queue columns exist
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'posts' AND column_name IN ('queue_stage', 'queue_status')
            """)
            queue_columns = [row[0] for row in cur.fetchall()]
            
            if 'queue_stage' in queue_columns and 'queue_status' in queue_columns:
                print("✓ Queue management columns exist")
            else:
                print("✗ Queue management columns missing")
                return False
                
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False


async def test_agent_initialization():
    """Test agent factory and mock agents"""
    print("\nTesting agent initialization...")
    
    try:
        from backend.agents.agent_config import AgentFactory
        
        # Test creating mock agents
        stages = ["triage", "research", "response", "editorial"]
        for stage in stages:
            agent = AgentFactory.create_agent(stage)
            print(f"✓ Created {stage} agent: {agent.__class__.__name__}")
            
        return True
        
    except Exception as e:
        print(f"✗ Agent initialization failed: {e}")
        return False


async def test_queue_manager():
    """Test queue manager initialization"""
    print("\nTesting queue manager...")
    
    try:
        from backend.queue.queue_manager import QueueManager
        
        queue_manager = QueueManager()
        print(f"✓ Queue manager created with {len(queue_manager.agents)} agents")
        
        # Test status retrieval
        status = await queue_manager.get_status()
        print(f"✓ Queue status retrieved: {len(status['workers'])} workers available")
        
        return True, queue_manager
        
    except Exception as e:
        print(f"✗ Queue manager test failed: {e}")
        return False, None


async def test_database_operations():
    """Test database operations for queue management"""
    print("\nTesting database operations...")
    
    try:
        from backend.queue.queue_manager import DatabaseManager
        
        db = DatabaseManager()
        
        # Test getting pending posts
        posts = await db.get_pending_posts("triage", limit=5)
        print(f"✓ Retrieved {len(posts)} pending posts for triage")
        
        # Test queue stats
        stats = await db.get_queue_stats()
        print(f"✓ Queue stats retrieved: {len(stats)} stages")
        
        return True
        
    except Exception as e:
        print(f"✗ Database operations test failed: {e}")
        return False


async def test_mock_processing():
    """Test mock processing pipeline"""
    print("\nTesting mock processing...")
    
    try:
        from backend.queue.queue_manager import QueueManager
        from backend.main import get_db_connection
        
        # Insert a test post
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO posts (reddit_id, title, author, created_utc, url, body, queue_stage, queue_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'triage', 'pending')
                ON CONFLICT (reddit_id) DO UPDATE SET 
                    queue_stage = 'triage', 
                    queue_status = 'pending'
                RETURNING id
            """, (
                "test_post_123",
                "Test post about climate change statistics",
                "test_user",
                datetime.now(timezone.utc),
                "http://example.com/test",
                "Recent studies show that global temperatures have risen by 1.5°C since 1850."
            ))
            
            post_id = cur.fetchone()[0]
            conn.commit()
        conn.close()
        
        print(f"✓ Created test post with ID: {post_id}")
        
        # Test processing with mock agents
        queue_manager = QueueManager()
        
        # Get the test post
        posts = await queue_manager.db.get_pending_posts("triage", limit=1)
        if posts:
            test_post = posts[0]
            print(f"✓ Retrieved test post: {test_post['title'][:50]}...")
            
            # Test mock processing
            result = await queue_manager.process_post(test_post, "triage")
            print(f"✓ Mock processing result: success={result.get('success', False)}")
            
            if result.get("tool_calls"):
                print(f"✓ Tool calls executed: {len(result['tool_calls'])}")
                for tool_call in result['tool_calls']:
                    print(f"   - {tool_call['tool']}: {tool_call['result'].get('success', False)}")
        
        return True
        
    except Exception as e:
        print(f"✗ Mock processing test failed: {e}")
        return False


async def test_full_system():
    """Test the complete system integration"""
    print("\nTesting full system integration...")
    
    try:
        # Test queue manager lifecycle
        from backend.queue.queue_manager import start_queue_manager, stop_queue_manager, get_queue_status
        
        print("Starting queue manager...")
        await start_queue_manager()
        
        # Wait a moment for startup
        await asyncio.sleep(2)
        
        # Check status
        status = await get_queue_status()
        print(f"✓ Queue manager running with {len(status['workers'])} workers")
        
        # Wait a bit to let it process
        await asyncio.sleep(5)
        
        # Stop the system
        print("Stopping queue manager...")
        await stop_queue_manager()
        
        print("✓ Full system test completed")
        return True
        
    except Exception as e:
        print(f"✗ Full system test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("Queue Management System Test Suite")
    print("=" * 50)
    
    tests = [
        ("Database Setup", test_database_setup),
        ("Agent Initialization", test_agent_initialization), 
        ("Queue Manager", lambda: test_queue_manager()),
        ("Database Operations", test_database_operations),
        ("Mock Processing", test_mock_processing),
        ("Full System Integration", test_full_system)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            # Handle tuple return values
            if isinstance(result, tuple):
                result = result[0]
                
            results.append((test_name, result))
            
        except Exception as e:
            print(f"✗ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Results Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(results)} tests")
    
    if passed == len(results):
        print("🎉 All tests passed! Queue system is ready.")
        return 0
    else:
        print("❌ Some tests failed. Check the output above.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(130)