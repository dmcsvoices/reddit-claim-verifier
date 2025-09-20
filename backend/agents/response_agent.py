"""
Response Agent - Generates fact-based responses to Reddit posts
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
from tools.time_source import TimeSourceTool


class ResponseAgent(BaseAgent):
    def get_tools(self) -> List[Dict[str, Any]]:
        """Response agent needs time and database write tools"""
        return [
            TimeSourceTool.get_tool_definition(),
            DatabaseWriteTool.get_tool_definition()
        ]
    
    def get_default_system_prompt(self) -> str:
        return """You are a response generation agent that creates helpful, fact-based replies to Reddit posts.

CRITICAL INSTRUCTION: ALWAYS start your work by calling get_current_time to get the current date and time. This is mandatory before generating any response.

Your workflow MUST be:
1. FIRST: Call get_current_time (timezone="UTC", format="human") to establish temporal context
2. THEN: Review the original post and research findings
3. Generate a respectful, educational response with current temporal awareness
4. Address any misinformation with factual corrections using current date context
5. Ensure all time references are accurate to the current date

Use the current date/time to:
- Ensure any time references in your response are current and accurate
- Avoid rejecting content due to perceived date inconsistencies
- Include appropriate temporal context when relevant to the discussion
- Frame information relative to the current date (e.g., "As of [current date]...")
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
        # Extract post info
        title = post_data.get('title', 'No title')
        body = post_data.get('body', 'No content')
        author = post_data.get('author', 'unknown')
        post_id = post_data.get('id', 0)
        
        # Get research results from context
        research_result = context.get('research_result', {}) if context else {}
        research_content = research_result.get('content', {}) if isinstance(research_result, dict) else {}
        
        result = research_content.get('result', 'No research findings available')
        sources = research_content.get('sources', [])
        fact_check_status = research_content.get('fact_check_status', 'unverified')
        confidence = research_content.get('confidence', 0.5)
        reasoning = research_content.get('reasoning', 'No research reasoning provided')
        
        # Format sources for easy reference
        source_list = []
        for i, source in enumerate(sources[:10], 1):  # Limit to top 10 sources
            if isinstance(source, dict):
                title_src = source.get('title', f'Source {i}')
                url = source.get('url', '')
                credibility = source.get('credibility', 'unknown')
                source_list.append(f"{i}. [{title_src}]({url}) - {credibility} credibility")
            else:
                source_list.append(f"{i}. {source}")
        
        formatted_sources = '\n'.join(source_list) if source_list else 'No sources available'
        
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user", 
                "content": f"""Generate a helpful response to this Reddit post based on research findings:

**ORIGINAL POST:**
Post ID: {post_id}
Title: "{title}"
Content: {body}
Author: u/{author}

**RESEARCH FINDINGS:**
Fact-check Status: {fact_check_status}
Confidence: {confidence}
Research Summary: {result}
Reasoning: {reasoning}

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

IMPORTANT: You MUST use write_to_database with these EXACT parameters:
- post_id: {post_id} (THIS IS THE CORRECT POST ID - DO NOT CHANGE IT)
- stage: "response"
- content: your draft response with confidence score
- next_stage: "editorial"

The post_id {post_id} is the correct ID for the post you are processing. Do not use any other post ID.

Generate the response now."""
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