#!/usr/bin/env python3
"""
Debug Reddit authentication with detailed error information
"""
import os
import sys
import requests
import base64
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

print("Reddit Authentication Debug")
print("=" * 40)

# Get credentials
client_id = os.getenv("REDDIT_CLIENT_ID")
client_secret = os.getenv("REDDIT_CLIENT_SECRET") 
username = os.getenv("REDDIT_USERNAME")
password = os.getenv("REDDIT_PASSWORD")
user_agent = os.getenv("REDDIT_USER_AGENT", "reddit-claim-verifier/1.0")

print(f"Client ID: {client_id}")
print(f"Client Secret: {client_secret[:5]}...{client_secret[-3:] if len(client_secret) > 8 else 'TOO_SHORT'}")
print(f"Username: {username}")
print(f"Password: {'*' * len(password) if password else 'NOT_SET'}")
print(f"User Agent: {user_agent}")
print()

# Test direct API call
print("Testing direct Reddit API call...")

# Create basic auth header
auth_string = f"{client_id}:{client_secret}"
auth_bytes = auth_string.encode('ascii')
auth_header = base64.b64encode(auth_bytes).decode('ascii')

headers = {
    'Authorization': f'Basic {auth_header}',
    'User-Agent': user_agent
}

data = {
    'grant_type': 'password',
    'username': username,
    'password': password
}

try:
    response = requests.post('https://www.reddit.com/api/v1/access_token', 
                           headers=headers, data=data, timeout=10)
    
    print(f"Response Status: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    
    if response.status_code == 200:
        token_data = response.json()
        print("✅ Authentication successful!")
        print(f"Access Token: {token_data.get('access_token', '')[:10]}...")
        print(f"Token Type: {token_data.get('token_type', '')}")
        print(f"Expires In: {token_data.get('expires_in', '')} seconds")
        
    elif response.status_code == 401:
        print("❌ 401 Unauthorized")
        error_text = response.text
        print(f"Error Response: {error_text}")
        
        if "invalid_grant" in error_text:
            print("\n🔍 Diagnosis: Invalid username/password")
            print("Solutions:")
            print("1. Check your Reddit username and password are correct")
            print("2. If you have 2FA enabled, you need an app password")
            print("3. Try logging into Reddit manually to verify credentials")
            
        elif "unauthorized_client" in error_text:
            print("\n🔍 Diagnosis: Invalid client credentials")
            print("Solutions:")
            print("1. Verify your Client ID and Client Secret from https://www.reddit.com/prefs/apps")
            print("2. Make sure your app type is 'script'")
            print("3. Check for any extra spaces or characters in credentials")
            
    else:
        print(f"❌ Unexpected status code: {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.Timeout:
    print("❌ Request timed out")
except requests.exceptions.RequestException as e:
    print(f"❌ Request error: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")

print("\n" + "=" * 40)
print("Next steps:")
print("1. Go to https://www.reddit.com/prefs/apps")
print("2. Verify your app exists and is type 'script'")
print("3. Check Client ID and Secret match exactly")
print("4. If you have 2FA, generate an app password")