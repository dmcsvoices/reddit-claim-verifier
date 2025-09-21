"""
Triage Agent - Identifies posts that make factual claims worth fact-checking
"""
import sys
import re
import json
from typing import Dict, Any, List
from pathlib import Path

# Add backend directory to Python path for absolute imports
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from agents.base_agent import BaseAgent
from tools.database_write import DatabaseWriteTool
from tools.time_source import TimeSourceTool


class TriageResponse:
    """JSON schema for triage response"""

    @staticmethod
    def get_json_schema():
        return {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["RESEARCH_NEEDED", "REJECTED"],
                    "description": "The triage decision"
                },
                "priority": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Priority level from 1-10"
                },
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of factual claims identified"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of the decision"
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Confidence level from 0.0-1.0"
                }
            },
            "required": ["decision", "priority", "claims", "reasoning", "confidence"],
            "additionalProperties": False
        }


class TriageAgent(BaseAgent):
    def get_tools(self) -> List[Dict[str, Any]]:
        """Triage agent has access to time information for context"""
        return [
            TimeSourceTool.get_tool_definition()
        ]
    
    def get_default_system_prompt(self) -> str:
        return """You are a triage agent that identifies Reddit posts making factual claims worth researching.

CRITICAL INSTRUCTION: ALWAYS start your work by calling get_current_time to get the current date and time. This is mandatory before analyzing any content.

Your workflow MUST be:
1. FIRST: Call get_current_time (timezone="UTC", format="human") to establish temporal context
2. THEN: Analyze the post title and content for factual claims
3. Determine if the claims are worth fact-checking based on current date context
4. Extract specific claims that can be verified
5. Assess the post's potential impact and engagement

Use the current date/time to:
- Assess if claims are recent or outdated
- Determine temporal relevance of posts  
- Check if claims relate to current events
- Avoid rejecting content due to perceived date inconsistencies

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

OUTPUT REQUIREMENTS:
You MUST respond ONLY in valid JSON format. Do not include any text before or after the JSON object.
After your analysis, you MUST provide a valid JSON object with this exact structure.
CRITICAL: The JSON must be syntactically correct and contain ALL required fields.

```json
{
  "decision": "RESEARCH_NEEDED",
  "priority": 7,
  "claims": ["claim 1", "claim 2"],
  "reasoning": "your reasoning here",
  "confidence": 0.8
}
```

STRICT JSON REQUIREMENTS:
- decision: MUST be exactly "RESEARCH_NEEDED" or "REJECTED" (no other values)
- priority: MUST be an integer from 1 to 10
- claims: MUST be an array of strings (even if empty: [])
- reasoning: MUST be a string explaining your decision
- confidence: MUST be a decimal between 0.0 and 1.0
- ALL fields are required - do not omit any
- Ensure proper JSON syntax with correct quotes, commas, and brackets
- Do not include any text before or after the JSON object

EXAMPLE OUTPUT:
<think>
I need to analyze this post about coffee and health claims...
</think>

This post makes specific statistical claims about health that could mislead readers.

```json
{
  "decision": "RESEARCH_NEEDED",
  "priority": 7,
  "claims": ["Coffee reduces cancer risk by 30%", "Study followed 50,000 participants"],
  "reasoning": "Makes specific health claims with statistics that could mislead if false",
  "confidence": 0.8
}
```"""
    
    def build_messages(self, post_data: Dict[str, Any], context: Dict[str, Any] = None) -> List[Dict[str, str]]:
        # Extract post info with safe defaults
        title = post_data.get('title', 'No title')
        author = post_data.get('author', 'unknown')
        body = post_data.get('body', 'No text content')
        url = post_data.get('url', 'No URL')
        post_id = post_data.get('id', 0)
        
        # Calculate post age from created_utc if available
        created_utc = post_data.get('created_utc')
        if created_utc:
            from datetime import datetime, timezone
            try:
                if isinstance(created_utc, str):
                    created_time = datetime.fromisoformat(created_utc.replace('Z', '+00:00'))
                else:
                    created_time = created_utc
                age_hours = (datetime.now(timezone.utc) - created_time).total_seconds() / 3600
                post_age_str = f"{age_hours:.1f} hours ago"
            except:
                post_age_str = "unknown"
        else:
            post_age_str = "unknown"
        
        # Extract engagement metrics (may not be available in queue data)
        upvotes = post_data.get('upvotes', 'unknown')
        comments = post_data.get('num_comments', 'unknown')
        
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user", 
                "content": f"""Analyze this Reddit post for factual claims that need verification:

**POST DETAILS:**
Post ID: {post_id}
Title: {title}
Author: u/{author}
Posted: {post_age_str}
Upvotes: {upvotes}
Comments: {comments}

**CONTENT:**
{body}

**URL/LINK:** {url}

**YOUR TASK:**
1. Identify any specific factual claims in the title and content
2. Evaluate if this post meets our fact-checking criteria
3. If it qualifies: extract claims, assign priority (1-10), categorize
4. If it does not qualify: explain why and reject

IMPORTANT: After your analysis, you MUST provide your response as a JSON object in exactly this format:

```json
{{
  "decision": "RESEARCH_NEEDED",
  "priority": 7,
  "claims": ["claim 1", "claim 2"],
  "reasoning": "your reasoning here",
  "confidence": 0.8
}}
```

Note: 
- priority must be a number 1-10
- confidence must be a decimal 0.0-1.0
- claims must be a list of strings"""
            }
        ]
    
    def parse_triage_response(self, content: str) -> Dict[str, Any]:
        """Parse the JSON response from the LLM"""
        try:
            # Remove <think> tags if present (for Qwen model)
            content_cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)

            # Extract JSON from code blocks (```json ... ```)
            json_pattern = r'```json\s*(.*?)\s*```'
            json_match = re.search(json_pattern, content_cleaned, re.DOTALL | re.MULTILINE)

            if json_match:
                json_str = json_match.group(1).strip()
            else:
                # Fallback: try to find JSON object without code blocks
                # Look for { ... } pattern, find the last complete JSON object
                json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                json_matches = re.findall(json_pattern, content_cleaned, re.DOTALL)
                if json_matches:
                    # Take the last (and likely most complete) JSON object
                    json_str = json_matches[-1]
                else:
                    return {
                        "success": False,
                        "error": "No JSON object found in response"
                    }

            # Clean up the JSON string - fix common issues
            json_str = json_str.strip()

            # Remove common prefixes that models add
            if json_str.startswith('```json'):
                json_str = json_str[7:]
            if json_str.endswith('```'):
                json_str = json_str[:-3]

            json_str = json_str.strip()

            # Fix the "or" pattern that the model might include
            json_str = re.sub(r'"RESEARCH_NEEDED"\s+or\s+"REJECTED"', '"RESEARCH_NEEDED"', json_str)
            json_str = re.sub(r'"REJECTED"\s+or\s+"RESEARCH_NEEDED"', '"REJECTED"', json_str)

            # Fix common JSON issues
            # Remove trailing commas before closing braces/brackets
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            
            # Parse the JSON with error recovery
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"   ⚠️  JSON parse error: {e}")
                print(f"   📄 Attempting JSON repair on: {json_str[:200]}...")

                # Attempt to fix common JSON issues
                try:
                    # Try to fix incomplete JSON by adding missing closing braces
                    fixed_json = json_str

                    # Count open/close braces and brackets
                    open_braces = fixed_json.count('{')
                    close_braces = fixed_json.count('}')
                    open_brackets = fixed_json.count('[')
                    close_brackets = fixed_json.count(']')

                    # Add missing closing braces/brackets
                    if open_braces > close_braces:
                        fixed_json += '}' * (open_braces - close_braces)
                    if open_brackets > close_brackets:
                        fixed_json += ']' * (open_brackets - close_brackets)

                    # Try parsing the fixed JSON
                    result = json.loads(fixed_json)
                    print(f"   ✅ JSON repair successful!")

                except json.JSONDecodeError:
                    # If repair fails, return original error
                    return {
                        "success": False,
                        "error": f"Invalid JSON format: {str(e)}",
                        "attempted_repair": True
                    }
            
            # Handle common field name variations the model might use
            if "claims_identified" in result and "claims" not in result:
                result["claims"] = result.pop("claims_identified")

            if "claims_list" in result and "claims" not in result:
                result["claims"] = result.pop("claims_list")

            # Validate required fields
            if "decision" not in result:
                return {"success": False, "error": "Missing 'decision' field in JSON"}

            if result["decision"] not in ["RESEARCH_NEEDED", "REJECTED"]:
                return {"success": False, "error": "Invalid decision value, must be RESEARCH_NEEDED or REJECTED"}

            # Set defaults for optional fields
            result.setdefault("priority", 5)
            result.setdefault("claims", [])
            result.setdefault("reasoning", "No reasoning provided")
            result.setdefault("confidence", 0.5)
            
            # Validate data types
            try:
                result["priority"] = int(result["priority"])
                result["confidence"] = float(result["confidence"])
                if not isinstance(result["claims"], list):
                    result["claims"] = []
            except (ValueError, TypeError):
                return {"success": False, "error": "Invalid data types in JSON response"}
            
            return {"success": True, "parsed_result": result}
            
        except Exception as e:
            return {"success": False, "error": f"Parser error: {str(e)}"}
    
    async def process(self, post_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Override process to handle text parsing instead of tool calls"""
        try:
            # Get LLM response
            messages = self.build_messages(post_data, context)
            response = await self.call_llm(messages, self.tools)
            
            if "error" in response:
                return response
            
            # Handle different response structures from different APIs
            if "message" in response:
                # Ollama/LM Studio format
                message = response.get("message", {})
                content = message.get("content", "")
            else:
                # Together AI format (returns content directly)
                content = response.get("content", "")

            # Debug: Print the raw content before parsing
            print(f"🔍 TRIAGE DEBUG - Raw content from LLM ({len(content) if content else 0} chars):")
            if content:
                print(f"   Content: {repr(content[:500])}")  # First 500 chars with repr to see special chars
                if len(content) > 500:
                    print(f"   ... (truncated from {len(content)} total chars)")
            else:
                print(f"   Content is empty or None")

            # Parse the structured response
            parse_result = self.parse_triage_response(content)
            
            if not parse_result["success"]:
                return {
                    "success": False,
                    "error": f"Failed to parse response: {parse_result['error']}",
                    "raw_content": content
                }
            
            parsed = parse_result["parsed_result"]
            post_id = post_data.get("id")
            
            # Write to database based on parsed result
            from tools.database_write import DatabaseWriteTool
            db_tool = DatabaseWriteTool()
            
            next_stage = "research" if parsed["decision"] == "RESEARCH_NEEDED" else "rejected"
            
            print(f"🔍 TRIAGE AGENT - Post {post_id}:")
            print(f"   Decision: {parsed['decision']}")
            print(f"   Next stage: {next_stage}")
            print(f"   Priority: {parsed['priority']}")
            print(f"   Claims: {parsed['claims']}")
            print(f"   Confidence: {parsed['confidence']}")
            print(f"   Writing to database...")
            
            db_result = await db_tool.execute(
                post_id=post_id,
                stage="triage",
                content={
                    "result": f"Triage decision: {parsed['decision']}",
                    "claims_identified": parsed["claims"],
                    "priority": parsed["priority"],
                    "reasoning": parsed["reasoning"],
                    "confidence": parsed["confidence"],
                    "fact_check_status": "pending" if next_stage == "research" else "rejected"
                },
                next_stage=next_stage,
                priority=parsed["priority"]
            )
            
            if db_result["success"]:
                print(f"✅ TRIAGE DB WRITE - Post {post_id} successfully written to database")
                print(f"   Result ID: {db_result.get('result_id')}")
                print(f"   Next stage set to: {db_result.get('next_stage')}")
            else:
                print(f"❌ TRIAGE DB WRITE FAILED - Post {post_id}: {db_result.get('error')}")
            
            return {
                "success": True,
                "content": content,
                "parsed_result": parsed,
                "tool_calls": [{
                    "tool": "write_to_database",
                    "result": db_result
                }],
                "usage": response.get("usage", {})
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Triage processing failed: {str(e)}"
            }

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