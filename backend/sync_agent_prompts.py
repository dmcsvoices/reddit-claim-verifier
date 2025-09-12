#!/usr/bin/env python3
"""
Sync Agent Prompts - Updates database with latest default system prompts from agent classes
This ensures the frontend shows the most recent prompt versions with time tool instructions.
"""
import sys
import os
import psycopg
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from agents.triage_agent import TriageAgent
from agents.research_agent import ResearchAgent
from agents.response_agent import ResponseAgent
from agents.editorial_agent import EditorialAgent

def get_db_connection():
    """Get database connection using environment variables"""
    try:
        # Load environment variables 
        from dotenv import load_dotenv
        load_dotenv()
        
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '5443')
        db_name = os.getenv('DB_NAME', 'redditmon')
        user = os.getenv('DB_USER', 'redditmon') 
        password = os.getenv('DB_PASSWORD', 'supersecret')
        
        return psycopg.connect(
            host=host,
            port=port,
            dbname=db_name,
            user=user,
            password=password
        )
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def sync_agent_prompts():
    """Sync database agent_prompts table with latest default prompts from agent classes"""
    print("🔄 SYNCING AGENT PROMPTS WITH LATEST DEFAULTS")
    print("=" * 60)
    
    # Create agent instances to get latest default prompts
    agents = {
        'triage': TriageAgent("sync-model", "http://localhost:11434"),
        'research': ResearchAgent("sync-model", "http://localhost:11434"),
        'response': ResponseAgent("sync-model", "http://localhost:11434"),
        'editorial': EditorialAgent("sync-model", "http://localhost:11434")
    }
    
    # Connect to database
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to connect to database")
        return False
        
    try:
        with conn.cursor() as cur:
            synced_count = 0
            
            for stage, agent in agents.items():
                print(f"\n🔧 Processing {stage.upper()} agent...")
                
                # Get the latest default prompt from the agent class
                latest_prompt = agent.get_default_system_prompt()
                print(f"   📝 Latest prompt length: {len(latest_prompt)} characters")
                
                # Check if this prompt already exists in database
                cur.execute("""
                    SELECT system_prompt, version FROM agent_prompts 
                    WHERE agent_stage = %s 
                    ORDER BY version DESC LIMIT 1
                """, (stage,))
                
                result = cur.fetchone()
                current_prompt = result[0] if result else None
                current_version = result[1] if result else 0
                
                if current_prompt == latest_prompt:
                    print(f"   ✅ Prompt is already up-to-date (version {current_version})")
                    continue
                    
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
                
                print(f"   ✅ Updated to version {new_version}")
                print(f"   🔍 Key changes detected:")
                
                # Show key differences
                if current_prompt and "CRITICAL INSTRUCTION" in latest_prompt and "CRITICAL INSTRUCTION" not in current_prompt:
                    print(f"      + Added CRITICAL INSTRUCTION for mandatory time tool usage")
                if current_prompt and "FIRST: Call get_current_time" in latest_prompt and "FIRST: Call get_current_time" not in current_prompt:
                    print(f"      + Added mandatory first step: get_current_time call")
                if current_prompt and "workflow MUST be" in latest_prompt and "workflow MUST be" not in current_prompt:
                    print(f"      + Added mandatory workflow structure")
                    
                synced_count += 1
                
            # Commit all changes
            conn.commit()
            
            print(f"\n📊 SYNC SUMMARY:")
            print(f"   Total agents processed: {len(agents)}")
            print(f"   Prompts updated: {synced_count}")
            print(f"   Prompts unchanged: {len(agents) - synced_count}")
            
            if synced_count > 0:
                print(f"\n🎉 SUCCESS: Database prompts synced with latest time tool instructions!")
                print(f"   Frontend will now show updated prompts with time-first workflow.")
            else:
                print(f"\n✅ All prompts were already up-to-date.")
                
            return True
            
    except Exception as e:
        print(f"❌ Error syncing prompts: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    # Set environment variable to avoid BraveSearch error during agent instantiation
    os.environ["BRAVE_API_KEY"] = "sync_script_key"
    
    success = sync_agent_prompts()
    sys.exit(0 if success else 1)