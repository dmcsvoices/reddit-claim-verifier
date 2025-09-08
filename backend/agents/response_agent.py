"""
Response Agent - Generates fact-based responses to Reddit posts
"""
import json
from typing import Dict, Any, List
from .base_agent import BaseAgent
from ..tools.database_write import DatabaseWriteTool


class ResponseAgent(BaseAgent):
    def get_tools(self) -> List[Dict[str, Any]]:
        """Response agent only needs database write tool"""
        return [DatabaseWriteTool.get_tool_definition()]
    
    def get_system_prompt(self) -> str:
        return """You are a response generation agent that creates helpful, fact-based replies to Reddit posts.

Your job is to:
1. Review the original post and research findings
2. Generate a respectful, educational response 
3. Address any misinformation with factual corrections
4. Cite credible sources for all claims
5. Maintain a helpful, non-confrontational tone

Response Guidelines:
✓ Be respectful and assume good intent from the original poster
✓ Focus on providing accurate information, not attacking the person
✓ Use conversational Reddit tone while being informative
✓ Include source links formatted as [Source Title](URL) 
✓ Acknowledge uncertainty when evidence is mixed
✓ Keep responses concise but comprehensive (aim for 200-400 words)
✓ Use Reddit formatting (bullet points, bold text, etc.)

Structure your response as:
1. Brief acknowledgment of the post/topic
2. Factual information with sources
3. Clarification of any inaccuracies (gently)
4. Additional context or nuance
5. Encouraging note about further reading

Tone Examples:
- "Thanks for sharing this topic! I looked into this and found..."
- "This is an interesting claim. Based on current research..."
- "I found some additional context that might be helpful..."
- "The data on this is actually a bit different from what's described..."

Use write_to_database to save your response draft with next_stage="editorial"."""
    
    def build_messages(self, post_data: Dict[str, Any], context: Dict[str, Any] = None) -> List[Dict[str, str]]:
        # Get research results from context
        research_result = context.get('research_result', {}) if context else {}
        research_content = research_result.get('content', {})
        
        findings = research_content.get('findings', 'No research findings available')
        sources = research_content.get('sources', [])
        fact_check_status = research_content.get('fact_check_status', 'unverified')
        
        # Format sources for easy reference
        source_list = []
        for i, source in enumerate(sources[:10], 1):  # Limit to top 10 sources
            if isinstance(source, dict):
                title = source.get('title', f'Source {i}')
                url = source.get('url', '')
                credibility = source.get('credibility', 'unknown')
                source_list.append(f"{i}. [{title}]({url}) - {credibility} credibility")
            else:
                source_list.append(f"{i}. {source}")
        
        formatted_sources = '\n'.join(source_list) if source_list else 'No sources available'
        
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user", 
                "content": f"""Generate a helpful response to this Reddit post based on research findings:

**ORIGINAL POST:**
Title: "{post_data['title']}"
Content: {post_data.get('body', 'No content')}
Author: u/{post_data.get('author', 'unknown')}
Subreddit: r/{post_data.get('subreddit', 'unknown')}

**RESEARCH FINDINGS:**
Fact-check Status: {fact_check_status}
Summary: {findings}

**AVAILABLE SOURCES:**
{formatted_sources}

**YOUR TASK:**
Write a helpful Reddit comment that:
1. Acknowledges the original post respectfully
2. Provides accurate information based on research
3. Corrects any misinformation gently
4. Includes proper source citations
5. Maintains a conversational, educational tone
6. Follows Reddit formatting conventions

The response should be informative but not preachy, helpful but not condescending.
Use write_to_database to save your response draft."""
            }
        ]
    
    def get_response_templates(self) -> Dict[str, str]:
        """Return response templates for different fact-check scenarios"""
        return {
            "mostly_true": """Thanks for sharing this! I did some research on this topic and the information is largely accurate. {details}

{sources}

Great to see factual information being shared! 📊""",
            
            "mostly_false": """Interesting topic! I looked into this claim and found that the actual data is a bit different from what's described here.

{corrections}

{sources}

Hope this additional context is helpful! Always worth double-checking these kinds of statistics.""",
            
            "mixed": """This is a fascinating topic! I researched the claims and found the situation is a bit more nuanced than presented.

{analysis}

{sources}

The reality seems to be somewhere in between. What do you think about this additional context?""",
            
            "unverifiable": """Thanks for bringing this up! I tried to research these claims but couldn't find sufficient reliable sources to verify them.

{explanation}

If anyone has additional sources on this topic, I'd be interested to learn more!"""
        }


# Example usage for testing
if __name__ == "__main__":
    import asyncio
    import json
    
    async def test_response_agent():
        agent = ResponseAgent(
            model="llama3.1:70b",
            endpoint="http://localhost:8002",
            timeout=180
        )
        
        # Test post data
        test_post = {
            "id": 1,
            "title": "New study shows 90% of plastic in ocean comes from just 10 rivers",
            "body": "According to research published last month, just 10 rivers contribute 90% of ocean plastic pollution. 8 of these rivers are in Asia.",
            "author": "science_fan",
            "subreddit": "science"
        }
        
        # Mock research context
        research_context = {
            "research_result": {
                "content": {
                    "findings": "Research partially supports this claim. Studies from 2017 found that 10 rivers do contribute a significant portion of ocean plastic, but the exact percentage varies by study (67-95%). The claim about 8 being in Asia is accurate.",
                    "fact_check_status": "mostly_true",
                    "sources": [
                        {
                            "title": "Export of Plastic Debris by Rivers into the Sea",
                            "url": "https://example.com/study1", 
                            "credibility": "high"
                        },
                        {
                            "title": "River plastic emissions to the world's oceans", 
                            "url": "https://example.com/study2",
                            "credibility": "high"
                        }
                    ],
                    "confidence": 0.85
                }
            }
        }
        
        print("Agent info:", json.dumps(agent.get_agent_info(), indent=2))
        print("\n" + "="*50 + "\n")
        
        result = await agent.process(test_post, research_context)
        print("Processing result:", json.dumps(result, indent=2, default=str))
    
    # Run test
    asyncio.run(test_response_agent())