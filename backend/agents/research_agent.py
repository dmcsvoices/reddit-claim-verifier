"""
Research Agent - Researches factual claims using web search
"""
import json
from typing import Dict, Any, List
from .base_agent import BaseAgent
from ..tools.database_write import DatabaseWriteTool
from ..tools.brave_search import BraveSearchTool


class ResearchAgent(BaseAgent):
    def get_tools(self) -> List[Dict[str, Any]]:
        """Research agent needs both search and database tools"""
        return [
            BraveSearchTool.get_tool_definition(),
            DatabaseWriteTool.get_tool_definition()
        ]
    
    def get_system_prompt(self) -> str:
        return """You are a research agent that investigates factual claims using web search.

Your job is to:
1. Review claims identified by the triage agent
2. Use web search to find credible sources about each claim
3. Analyze evidence for and against each claim
4. Assess source credibility and recency
5. Synthesize findings into a research report

Research Strategy:
1. Search for primary sources (research papers, official statistics, government data)
2. Look for recent information and check if claims are outdated
3. Search for contradicting evidence and alternative viewpoints  
4. Verify through multiple independent sources
5. Note the credibility and potential bias of each source

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
        # Get triage results from context
        triage_result = context.get('triage_result', {}) if context else {}
        claims = triage_result.get('content', {}).get('claims_identified', [])
        priority = triage_result.get('content', {}).get('priority', 5)
        
        if not claims:
            # Fallback if no triage context - extract from post directly
            claims = [f"Claims from: {post_data['title']}"]
        
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user", 
                "content": f"""Research the factual claims from this Reddit post:

**ORIGINAL POST:**
Title: "{post_data['title']}"
Content: {post_data.get('body', 'No content')}
Subreddit: r/{post_data.get('subreddit', 'unknown')}
Priority: {priority}/10

**CLAIMS TO RESEARCH:**
{json.dumps(claims, indent=2)}

**YOUR RESEARCH PROCESS:**
For EACH claim:
1. Use brave_web_search with specific queries
2. Search for primary sources and authoritative information
3. Look for both supporting and contradicting evidence
4. Verify information through multiple independent sources
5. Check recency and relevance of sources

After researching all claims, use write_to_database to record:
- Summary of findings for each claim
- Source credibility assessment
- Supporting vs contradicting evidence
- Overall fact-check conclusion
- Confidence in your assessment

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