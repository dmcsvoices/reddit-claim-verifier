"""
Triage Agent - Identifies posts that make factual claims worth fact-checking
"""
import sys
from typing import Dict, Any, List
from pathlib import Path

# Add backend directory to Python path for absolute imports
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from agents.base_agent import BaseAgent
from tools.database_write import DatabaseWriteTool


class TriageAgent(BaseAgent):
    def get_tools(self) -> List[Dict[str, Any]]:
        """Triage agent only needs database write tool"""
        return [DatabaseWriteTool.get_tool_definition()]
    
    def get_system_prompt(self) -> str:
        return """You are a triage agent that identifies Reddit posts making factual claims worth researching.

Your job is to:
1. Analyze the post title and content for factual claims
2. Determine if the claims are worth fact-checking
3. Extract specific claims that can be verified
4. Assess the post's potential impact and engagement

Criteria for fact-checking:
✓ Contains specific, verifiable factual claims (statistics, scientific facts, historical events)
✓ Claims are not obviously satirical, memes, or personal opinions
✓ Post has reasonable engagement (upvotes/comments) indicating reach
✓ Claims could potentially spread misinformation if false
✓ Claims are within recent timeframe or currently relevant topics

What to REJECT:
✗ Pure opinion posts ("I think...", "In my view...")
✗ Questions without claims ("What do you think about...?")
✗ Obviously satirical content or memes
✗ Very low engagement posts (unless very concerning claims)
✗ Personal anecdotes without broader factual claims
✗ Posts asking for advice or help

For posts that qualify, extract:
- Specific factual claims (be precise, quote exact claims)
- Priority level (1-10 based on potential harm/reach)
- Category tags (health, science, politics, technology, etc.)

Use the write_to_database tool to record your analysis. Set next_stage to "research" if the post qualifies for fact-checking, or "rejected" if it doesn't meet criteria."""
    
    def build_messages(self, post_data: Dict[str, Any], context: Dict[str, Any] = None) -> List[Dict[str, str]]:
        # Calculate engagement score for context
        upvotes = post_data.get('upvotes', 0)
        comments = post_data.get('num_comments', 0)
        engagement_score = upvotes + (comments * 2)  # Comments weighted higher
        
        post_age_hours = post_data.get('age_hours', 'unknown')
        
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user", 
                "content": f"""Analyze this Reddit post for factual claims that need verification:

**POST DETAILS:**
Title: "{post_data['title']}"
Author: u/{post_data.get('author', 'unknown')}
Subreddit: r/{post_data.get('subreddit', 'unknown')}
Posted: {post_age_hours} hours ago
Upvotes: {upvotes}
Comments: {comments}
Engagement Score: {engagement_score}

**CONTENT:**
{post_data.get('body', 'No text content')}

**URL/LINK:** {post_data.get('url', 'No URL')}

**YOUR TASK:**
1. Identify any specific factual claims in the title and content
2. Evaluate if this post meets our fact-checking criteria
3. If it qualifies: extract claims, assign priority, categorize
4. If it doesn't qualify: explain why and reject

Use the write_to_database tool with your analysis."""
            }
        ]
    
    def get_priority_guidelines(self) -> str:
        """Return guidelines for assigning priority scores"""
        return """
Priority Guidelines (1-10):
- 9-10: Health misinformation, emergency/safety claims, high viral potential
- 7-8: Scientific misinformation, political claims, moderate reach
- 5-6: Historical facts, technology claims, modest engagement
- 3-4: Minor factual disputes, low engagement
- 1-2: Trivial claims, very low impact
        """


# Example usage for testing
if __name__ == "__main__":
    import asyncio
    import json
    
    async def test_triage_agent():
        agent = TriageAgent(
            model="llama3.1:8b", 
            endpoint="http://localhost:8001"
        )
        
        # Test post with factual claims
        test_post = {
            "id": 1,
            "title": "New study shows 90% of plastic in ocean comes from just 10 rivers",
            "author": "science_fan",
            "subreddit": "science", 
            "body": "According to research published last month, just 10 rivers contribute 90% of ocean plastic pollution. 8 of these rivers are in Asia. This completely changes how we should approach ocean cleanup.",
            "url": "https://example.com/study",
            "upvotes": 1250,
            "num_comments": 89,
            "age_hours": 6
        }
        
        print("Agent info:", json.dumps(agent.get_agent_info(), indent=2))
        print("\n" + "="*50 + "\n")
        
        result = await agent.process(test_post)
        print("Processing result:", json.dumps(result, indent=2))
    
    # Run test
    asyncio.run(test_triage_agent())