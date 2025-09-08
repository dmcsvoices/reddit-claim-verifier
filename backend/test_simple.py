#!/usr/bin/env python3
"""
Simple test script to check if basic imports work
"""
import os

print("Testing basic imports...")
print(f"Python path: {os.sys.path}")

try:
    import psycopg
    print("✓ psycopg imported successfully")
    
    # Test database connection
    conn = psycopg.connect(
        host=os.getenv("DB_HOST", "db"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "redditmon"),
        user=os.getenv("DB_USER", "redditmon"),
        password=os.getenv("DB_PASSWORD", "supersecret")
    )
    
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
        print(f"✓ Database connection successful: {result}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Database test failed: {e}")

try:
    import praw
    print("✓ praw imported successfully")
except Exception as e:
    print(f"❌ praw import failed: {e}")

print("Basic import test completed")