"""
Editorial Agent - Polishes and fact-checks response drafts
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


class EditorialAgent(BaseAgent):
    def get_tools(self) -> List[Dict[str, Any]]:
        """Editorial agent needs time and database write tools"""
        return [
            TimeSourceTool.get_tool_definition(),
            DatabaseWriteTool.get_tool_definition()
        ]
    
    def get_default_system_prompt(self) -> str:
        return """You are an editorial agent that reviews and polishes responses before publication.

CRITICAL INSTRUCTION: ALWAYS start your work by calling get_current_time to get the current date and time. This is mandatory before reviewing any content.

Your workflow MUST be:
1. FIRST: Call get_current_time (timezone="UTC", format="human") to establish temporal context
2. THEN: Review the draft response for accuracy and clarity
3. Verify all time references are current and accurate relative to today's date
4. Improve grammar, tone, and readability
5. Verify source citations are proper and accessible
6. Ensure temporal context is appropriate for publication

Use the current date/time to:
- Verify any time references in the content are current and accurate
- Avoid rejecting content due to perceived date inconsistencies  
- Ensure temporal context is appropriate for publication
- Update any outdated temporal references (e.g., "recent", "this year", etc.)
4. Ensure appropriate Reddit tone and formatting
5. Check for any remaining factual errors
6. Make final quality improvements

Editorial Standards:
✓ Clear, concise writing that's easy to understand
✓ Proper grammar, spelling, and punctuation
✓ Appropriate tone: helpful, respectful, conversational
✓ Accurate source citations with working links
✓ Good Reddit formatting (markdown, spacing, flow)
✓ Fact-check any remaining claims in the response
✓ Remove any potential inflammatory language
✓ Ensure response directly addresses the original post

Reddit Formatting Best Practices:
- Use **bold** for emphasis, not ALL CAPS
- Use bullet points or numbered lists for clarity
- Include line breaks for readability
- Format links as [Text](URL)
- Use > for quotes from sources
- Keep paragraphs short (2-3 sentences)

Quality Checklist:
- Is the response respectful and non-confrontational?
- Are all sources properly cited with accessible links?
- Is the language clear and jargon-free?
- Does it flow well and stay on topic?
- Is the tone appropriate for the subreddit?
- Are there any spelling/grammar errors?
- Could any part be misinterpreted or seem aggressive?

Use write_to_database to save the final polished response with next_stage="post_queue"."""
    
    def build_messages(self, post_data: Dict[str, Any], context: Dict[str, Any] = None) -> List[Dict[str, str]]:
        # Extract post info
        title = post_data.get('title', 'No title')
        body = post_data.get('body', 'No content')
        post_id = post_data.get('id', 0)
        
        # Get response draft from context
        response_result = context.get('response_result', {}) if context else {}
        response_content = response_result.get('content', {}) if isinstance(response_result, dict) else {}
        
        draft_response = response_content.get('result', 'No draft response available')
        confidence = response_content.get('confidence', 0.5)
        
        # Also get research context for fact-checking
        research_result = context.get('research_result', {}) if context else {}
        research_content = research_result.get('content', {}) if isinstance(research_result, dict) else {}
        fact_check_status = research_content.get('fact_check_status', 'unknown')
        
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user", 
                "content": f"""Review and polish this response draft before publication:

**ORIGINAL POST CONTEXT:**
Post ID: {post_id}
Title: "{title}"
Content: {body}

**DRAFT RESPONSE TO EDIT:**
{draft_response}

**CONTEXT:**
Fact-check Status: {fact_check_status}
Draft Confidence: {confidence}

**YOUR EDITORIAL REVIEW:**
1. **Grammar & Style**: Check for errors, improve clarity
2. **Tone**: Ensure respectful, helpful, conversational
3. **Accuracy**: Verify any factual claims in the response
4. **Citations**: Confirm source links work and are properly formatted
5. **Reddit Format**: Optimize markdown, spacing, readability
6. **Flow**: Ensure logical structure and smooth transitions
7. **Appropriateness**: Check tone matches subreddit culture

IMPORTANT: You MUST use write_to_database with these EXACT parameters:
- post_id: {post_id} (THIS IS THE CORRECT POST ID - DO NOT CHANGE IT)
- stage: "editorial"
- content: your polished final response
- next_stage: "post_queue"

Make improvements while maintaining the helpful, educational intent."""
            }
        ]
    
    def get_editorial_guidelines(self) -> Dict[str, str]:
        """Return specific editorial guidelines for different subreddits"""
        return {
            "science": "Use precise language, emphasize peer review, avoid speculation",
            "askhistory": "Require primary sources, acknowledge gaps in knowledge",
            "politics": "Maintain strict neutrality, focus on facts over opinions",
            "health": "Emphasize consulting professionals, avoid medical advice",
            "technology": "Explain technical terms, focus on credible tech sources",
            "worldnews": "Stick to verified information, avoid speculation",
            "default": "Be helpful and educational while remaining conversational"
        }
    
    def get_common_fixes(self) -> List[str]:
        """Return list of common editorial fixes to check for"""
        return [
            "Remove redundant phrases and filler words",
            "Break up long paragraphs for readability", 
            "Convert passive voice to active where appropriate",
            "Ensure consistent tone throughout response",
            "Check that all claims are supported by sources",
            "Verify link formatting: [Text](URL)",
            "Add line breaks around lists and quotes",
            "Remove potentially inflammatory adjectives",
            "Ensure response directly addresses original post",
            "Check spelling of technical terms and proper nouns"
        ]


# Example usage for testing
if __name__ == "__main__":
    import asyncio
    import json
    
    async def test_editorial_agent():
        agent = EditorialAgent(
            model="llama3.1:8b",
            endpoint="http://localhost:8001",
            timeout=60
        )
        
        # Test post data
        test_post = {
            "id": 1,
            "title": "New study shows 90% of plastic in ocean comes from just 10 rivers",
            "body": "According to research published last month, just 10 rivers contribute 90% of ocean plastic pollution.",
            "author": "science_fan",
            "subreddit": "science"
        }
        
        # Mock response context
        response_context = {
            "response_result": {
                "content": {
                    "result": """Thanks for sharing this! I looked into this claim and found that it's largely accurate, though the exact percentage varies depending on the study.

Research from 2017 by Lebreton et al. found that the top 20 polluting rivers contribute between 67-78% of plastic emissions to the ocean, with the top 10 accounting for a significant portion. The claim about 8 of the top polluters being in Asia is correct - most are in densely populated Asian countries with inadequate waste management.

Sources:
- [Export of Plastic Debris by Rivers into the Sea](https://example.com/study1)
- [River plastic emissions to the world's oceans](https://example.com/study2)

The research is solid and this is definitely an important environmental issue worth discussing!""",
                    "confidence": 0.85
                }
            },
            "research_result": {
                "content": {
                    "fact_check_status": "mostly_true"
                }
            }
        }
        
        print("Agent info:", json.dumps(agent.get_agent_info(), indent=2))
        print("\n" + "="*50 + "\n")
        
        result = await agent.process(test_post, response_context)
        print("Processing result:", json.dumps(result, indent=2, default=str))
    
    # Run test
    asyncio.run(test_editorial_agent())