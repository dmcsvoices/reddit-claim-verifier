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

CRITICAL INSTRUCTION: ALWAYS start your work by calling get_current_time to get the current date and time. This is mandatory before beginning any research.

Your workflow MUST be:
1. FIRST: Call get_current_time (timezone="UTC", format="human") to establish temporal context
2. THEN: Review claims identified by the triage agent
3. Use web search to find credible sources about each claim (include current date in searches)
4. Analyze evidence for and against each claim with temporal awareness
5. Assess source credibility and recency relative to current date
6. Synthesize findings into a research report with temporal context

Use the current date/time to:
- Contextualize all search results with current date
- Assess if information is recent or outdated
- Include temporal context in research analysis
- Search for time-specific claims (e.g., "as of [current year]", "recent studies")
- Avoid rejecting content due to perceived date inconsistencies

Research Strategy:
1. MANDATORY: Get current date/time first
2. Search for primary sources (research papers, official statistics, government data)
3. Look for recent information and check if claims are outdated relative to current date
4. Search for contradicting evidence and alternative viewpoints  
5. Verify through multiple independent sources
6. Note the credibility and potential bias of each source

Source Credibility Guidelines:
- HIGH: Peer-reviewed research, government agencies, established scientific institutions
- MEDIUM: Reputable news organizations, industry reports, expert interviews
- LOW: Blogs, social media, opinion pieces, sites with clear bias
- AVOID: Known misinformation sites, conspiracy theory sources

For each claim:
- Search with multiple query variations
- Look for both supporting and contradicting evidence
- Check publication dates (prefer recent sources)
- Note if consensus exists or if topic is disputed

Use brave_web_search to research claims, then write_to_database to record findings.
Set next_stage to "response" if research is complete, or "rejected" if claims are unverifiable."""
    
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
                "content": f"""Research the factual claims from this Reddit post:

**ORIGINAL POST:**
Post ID: {post_id}
Title: "{title}"
Content: {body}
Priority: {priority}/10

**TRIAGE ANALYSIS:**
{reasoning}

**CLAIMS TO RESEARCH:**
{json.dumps(claims, indent=2)}

**YOUR RESEARCH PROCESS:**
For EACH claim:
1. Use brave_web_search with multiple specific queries
2. Search for primary sources and authoritative information
3. Look for both supporting and contradicting evidence
4. Verify information through multiple independent sources
5. Check recency and relevance of sources

After researching all claims, use write_to_database to record:
- post_id: {post_id}
- stage: "research"
- content: your findings with sources, fact_check_status, reasoning, confidence
- next_stage: "response" (if research complete) or "rejected" (if unverifiable)

Start your research now using the available tools."""
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