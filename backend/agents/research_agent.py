"""
Research Agent - Researches factual claims using web search
"""
import json
import sys
from typing import Dict, Any, List
from pathlib import Path

# Add backend directory to Python path for absolute imports
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from agents.base_agent import BaseAgent
from tools.database_write import DatabaseWriteTool
from tools.brave_search import BraveSearchTool
from tools.time_source import TimeSourceTool


class ResearchAgent(BaseAgent):
    def get_tools(self) -> List[Dict[str, Any]]:
        """Research agent needs search, database, and time tools"""
        return [
            TimeSourceTool.get_tool_definition(),
            BraveSearchTool.get_tool_definition(),
            DatabaseWriteTool.get_tool_definition()
        ]
    
    def get_default_system_prompt(self) -> str:
        return """You are a research agent that investigates factual claims using web search.

🚨 CRITICAL: You MUST complete ALL steps below in a SINGLE response. Do NOT stop after just one tool call.

MANDATORY WORKFLOW - COMPLETE ALL STEPS:

STEP 1: Call get_current_time (timezone="UTC", format="human") to establish temporal context
STEP 2: Use brave_web_search to research EACH claim provided by the triage agent
STEP 3: Call write_to_database to record your findings and advance the post

⚠️ IMPORTANT: Getting the current time is just the BEGINNING. You must continue with research and database write!

Your complete workflow:
1. 🕐 get_current_time - Get current date/time for context
2. 🔍 brave_web_search - Research each factual claim (multiple searches per claim)
3. 📝 write_to_database - Record findings and set next_stage

You MUST research claims using web search. For each claim:
- Search with multiple query variations
- Look for credible sources (research papers, government data, expert sources)
- Find both supporting and contradicting evidence
- Check publication dates and source credibility
- Note if scientific consensus exists

Source Credibility Priority:
- HIGH: Peer-reviewed research, government agencies, scientific institutions
- MEDIUM: Reputable news organizations, expert interviews, industry reports
- LOW: Blogs, opinion pieces, biased sources
- AVOID: Conspiracy sites, known misinformation sources

After researching all claims, you MUST call write_to_database with:
- post_id: [provided post ID]
- stage: "research"
- content: your research findings, sources, fact_check_status, confidence
- next_stage: "response" (if research complete) or "rejected" (if unverifiable)

🚨 REMEMBER: Complete ALL three steps in one response - time, search, database write!"""
    
    def build_messages(self, post_data: Dict[str, Any], context: Dict[str, Any] = None) -> List[Dict[str, str]]:
        # Extract post info
        title = post_data.get('title', 'No title')
        body = post_data.get('body', 'No content')
        post_id = post_data.get('id', 0)
        
        # Get triage results from context
        triage_result = context.get('triage_result', {}) if context else {}
        triage_content = triage_result.get('content', {}) if isinstance(triage_result, dict) else {}
        claims = triage_content.get('claims_identified', [])
        priority = triage_content.get('priority', 5)
        reasoning = triage_content.get('reasoning', 'No triage reasoning provided')
        
        if not claims:
            # Fallback if no triage context - extract from post directly
            claims = [f"Claims from: {title}"]
        
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user", 
                "content": f"🔍 RESEARCH TASK: Complete ALL three steps for this Reddit post:\n\n**ORIGINAL POST:**\nPost ID: {post_id}\nTitle: \"{title}\"\nContent: {body}\nPriority: {priority}/10\n\n**TRIAGE ANALYSIS:**\n{reasoning}\n\n**CLAIMS TO RESEARCH:**\n{json.dumps(claims, indent=2)}\n\n🚨 COMPLETE WORKFLOW REQUIRED:\n\nSTEP 1: Call get_current_time to establish current date/time context\nSTEP 2: Research EACH claim using brave_web_search:\n   - Use multiple search queries per claim\n   - Find credible sources (government data, research papers, expert sources)\n   - Look for both supporting and contradicting evidence\n   - Check source dates and credibility\nSTEP 3: Call write_to_database with EXACT parameters:\n   - post_id: {post_id}\n   - stage: \"research\"\n   - content: {{your research findings, sources, fact_check_status, confidence}}\n   - next_stage: \"response\" (if complete) or \"rejected\" (if unverifiable)\n\n⚠️ CRITICAL: You must complete ALL THREE steps in this single response. Do not stop after just getting the time!\n\nStart now by calling get_current_time, then research each claim, then write results to database."
            }
        ]
    
    def get_search_strategies(self) -> Dict[str, List[str]]:
        """Return search query strategies for different types of claims"""
        return {
            "statistics": [
                "{claim} official statistics",
                "{claim} government data",
                "{claim} research study",
                "\"{exact_statistic}\" source"
            ],
            "scientific": [
                "{claim} peer reviewed research",
                "{claim} scientific study 2024",
                "{claim} meta analysis",
                "{claim} expert consensus"
            ],
            "health": [
                "{claim} medical research",
                "{claim} clinical trial",
                "{claim} WHO CDC guidelines",
                "{claim} health authority"
            ],
            "historical": [
                "{claim} historical records",
                "{claim} primary sources",
                "{claim} academic history",
                "{claim} fact check"
            ],
            "general": [
                "{claim} fact check",
                "{claim} evidence",
                "{claim} debunked myth",
                "{claim} expert opinion"
            ]
        }


# Example usage for testing  
if __name__ == "__main__":
    import asyncio
    import json
    
    async def test_research_agent():
        agent = ResearchAgent(
            model="llama3.1:70b",
            endpoint="http://localhost:8002", 
            timeout=300
        )
        
        # Test post data
        test_post = {
            "id": 1,
            "title": "New study shows 90% of plastic in ocean comes from just 10 rivers",
            "body": "According to research published last month, just 10 rivers contribute 90% of ocean plastic pollution. 8 of these rivers are in Asia.",
            "subreddit": "science"
        }
        
        # Mock triage context
        triage_context = {
            "triage_result": {
                "content": {
                    "claims_identified": [
                        "10 rivers contribute 90% of ocean plastic pollution",
                        "8 of the top 10 polluting rivers are in Asia"
                    ],
                    "priority": 7
                }
            }
        }
        
        print("Agent info:", json.dumps(agent.get_agent_info(), indent=2))
        print("\n" + "="*50 + "\n")
        
        result = await agent.process(test_post, triage_context)
        print("Processing result:", json.dumps(result, indent=2, default=str))
    
    # Run test
    asyncio.run(test_research_agent())