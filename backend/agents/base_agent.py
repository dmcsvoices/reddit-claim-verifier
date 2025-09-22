"""
Base Agent class for LLM agents with Ollama tool support
"""
import json
import httpx
import sys
import os
import psycopg
import ollama
import asyncio
import subprocess
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path

# Add backend directory to Python path for absolute imports
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from tools.database_write import DatabaseWriteTool
from tools.brave_search import BraveSearchTool
from tools.time_source import get_time_tool


class BaseAgent(ABC):
    def __init__(self, model: str, endpoint: str, timeout: int = 60, endpoint_type: str = "custom", api_key_env: str = None):
        self.model = model
        self.endpoint = endpoint.rstrip('/')
        self.timeout = timeout
        self.endpoint_type = endpoint_type or "custom"
        self.api_key_env = api_key_env
        # Determine agent stage from class name (e.g., "TriageAgent" -> "triage")
        self.agent_stage = self.__class__.__name__.lower().replace('agent', '')
        self.tools = self.get_tools()
        self.tool_implementations = self.get_tool_implementations()
        
        # Validate model availability (non-blocking, only if event loop is running)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._validate_model_async())
        except RuntimeError:
            # No event loop running, skip async validation for now
            pass
    
    def _get_db_connection(self):
        """Get database connection"""
        return psycopg.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5443"),
            dbname=os.getenv("DB_NAME", "redditmon"),
            user=os.getenv("DB_USER", "redditmon"),
            password=os.getenv("DB_PASSWORD", "supersecret")
        )

    async def _record_fallback_event(self, post_id: int, stage: str, reason: str,
                                   search_failures: int = 0, search_successes: int = 0,
                                   error_details: Dict[str, Any] = None):
        """Record a fallback event to the database for tracking and analysis"""
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO fallback_events
                        (post_id, stage, reason, search_failures, search_successes, error_details)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        post_id,
                        stage,
                        reason,
                        search_failures,
                        search_successes,
                        json.dumps(error_details or {})
                    ))
                    conn.commit()
                    print(f"   📊 Fallback event recorded: post_id={post_id}, stage={stage}")
        except Exception as e:
            print(f"   ❌ Failed to record fallback event: {e}")

    async def _validate_model_async(self):
        """Validate that the configured model exists on the endpoint (non-blocking)"""
        try:
            await self.validate_model_availability()
        except Exception as e:
            print(f"⚠️  {self.agent_stage.upper()} model validation failed: {e}")
    
    async def validate_model_availability(self) -> bool:
        """Check if the configured model is available on the endpoint"""
        try:
            if ":1234" in self.endpoint:
                # LM Studio - check via OpenAI client
                return await self._check_lmstudio_model()
            else:
                # Ollama - check via Ollama client
                return await self._check_ollama_model()
        except Exception as e:
            print(f"❌ {self.agent_stage.upper()} model validation error: {e}")
            return False
    
    async def _check_lmstudio_model(self) -> bool:
        """Check if model is available in LM Studio"""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                base_url=f"{self.endpoint}/v1",
                api_key="lm-studio"
            )
            models = await client.models.list()
            available_models = [model.id for model in models.data]
            
            if self.model in available_models:
                print(f"✅ {self.agent_stage.upper()} model '{self.model}' found in LM Studio")
                return True
            else:
                print(f"⚠️  {self.agent_stage.upper()} model '{self.model}' not loaded in LM Studio")
                print(f"   Available models: {available_models}")
                return False
                
        except Exception as e:
            print(f"❌ {self.agent_stage.upper()} LM Studio model check failed: {e}")
            return False
    
    async def _check_ollama_model(self) -> bool:
        """Check if model is available in Ollama"""
        try:
            import ollama
            client = ollama.AsyncClient(host=self.endpoint if ":11434" not in self.endpoint else None)
            models = await client.list()
            available_models = [model['name'] for model in models['models']]
            
            if self.model in available_models:
                print(f"✅ {self.agent_stage.upper()} model '{self.model}' found in Ollama")
                return True
            else:
                print(f"⚠️  {self.agent_stage.upper()} model '{self.model}' not available in Ollama")
                print(f"   Available models: {available_models}")
                print(f"   Run: ollama pull {self.model}")
                return False
                
        except Exception as e:
            print(f"❌ {self.agent_stage.upper()} Ollama model check failed: {e}")
            return False
    
    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of tool definitions for this agent"""
        pass
    
    @abstractmethod
    def get_default_system_prompt(self) -> str:
        """Return the default system prompt for this agent"""
        pass
    
    def get_system_prompt(self) -> str:
        """Get system prompt from database, fallback to default"""
        try:
            conn = self._get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT system_prompt FROM agent_prompts 
                    WHERE agent_stage = %s AND is_active = true
                    ORDER BY version DESC LIMIT 1
                """, (self.agent_stage,))
                
                result = cur.fetchone()
                if result:
                    conn.close()
                    return result[0]
                else:
                    # No prompt in database, initialize with default
                    default_prompt = self.get_default_system_prompt()
                    cur.execute("""
                        INSERT INTO agent_prompts (agent_stage, system_prompt, version, is_active)
                        VALUES (%s, %s, 1, true)
                        ON CONFLICT (agent_stage) DO UPDATE SET 
                            system_prompt = EXCLUDED.system_prompt,
                            updated_at = NOW()
                    """, (self.agent_stage, default_prompt))
                    conn.commit()
                    conn.close()
                    return default_prompt
                
        except Exception as e:
            print(f"❌ ERROR: Could not fetch system prompt from database for {self.agent_stage}: {e}")
            print(f"⚠️ WARNING: This should not happen in production! Database prompts should always be available.")
            try:
                if conn:
                    conn.close()
            except:
                pass

        # Emergency fallback - this should never be reached in normal operation
        print(f"🚨 EMERGENCY FALLBACK: Using hardcoded prompt for {self.agent_stage} - DATABASE CONNECTION FAILED!")
        return self.get_default_system_prompt()
    
    @abstractmethod
    def build_messages(self, post_data: dict, context: dict = None) -> List[Dict[str, str]]:
        """Build the message array for the LLM request"""
        pass
    
    def get_tool_implementations(self) -> Dict[str, Any]:
        """Return mapping of tool names to their implementation functions"""
        print(f"🔧 {self.agent_stage.upper()} TOOL REGISTRATION:")
        
        implementations = {
            "write_to_database": DatabaseWriteTool().execute
        }
        print(f"   ✅ Registered: write_to_database (always available)")
        
        # Add Brave Search if this agent uses it
        for tool in self.tools:
            if tool["function"]["name"] == "brave_web_search":
                implementations["brave_web_search"] = BraveSearchTool().execute
                print(f"   ✅ Registered: brave_web_search (BraveSearchTool)")
                break
        
        # Add Time Tool if this agent uses it
        for tool in self.tools:
            if tool["function"]["name"] == "get_current_time":
                implementations["get_current_time"] = get_time_tool().execute
                print(f"   ✅ Registered: get_current_time (TimeSourceTool)")
                break
        
        print(f"   📊 Total tools registered: {len(implementations)}")
        return implementations
    
    async def call_llm(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a request to the configured LLM endpoint with proper tool support"""
        print(f"🌐 {self.agent_stage.upper()} API REQUEST:")
        print(f"   Model: {self.model}")
        print(f"   Endpoint: {self.endpoint}")
        print(f"   Endpoint Type: {self.endpoint_type}")
        print(f"   Tools available: {len(tools) if tools else 0}")
        if tools:
            tool_names = [tool.get('function', {}).get('name', 'unknown') for tool in tools]
            print(f"   Tool names: {tool_names}")

        # Route based on endpoint type
        if self.endpoint_type == "together":
            print(f"   🔄 Using Together AI API")
            return await self.call_together_api(messages, tools)
        elif self.endpoint_type == "lmstudio":
            print(f"   🔄 Using LM Studio Python API")
            return await self.call_lmstudio_python_api(messages, tools)
        elif self.endpoint_type == "ollama":
            print(f"   🔄 Using Ollama Python API")
            return await self.call_ollama_python_api(messages, tools)
        else:
            # Custom endpoint - try to detect by port for backward compatibility
            if ":1234" in self.endpoint:
                print(f"   🔄 Port 1234 detected - using LM Studio Python API")
                return await self.call_lmstudio_python_api(messages, tools)
            else:
                print(f"   🔄 Using Ollama Python API (default)")
                return await self.call_ollama_python_api(messages, tools)
    
    async def call_lmstudio_python_api(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Use LM Studio Python API with OpenAI client library"""
        print(f"🟦 {self.agent_stage.upper()} LM STUDIO PYTHON API REQUEST:")
        print(f"   Model: {self.model}")
        print(f"   Endpoint: {self.endpoint}")
        
        try:
            from openai import AsyncOpenAI
            
            # Connect to LM Studio using OpenAI client
            client = AsyncOpenAI(
                base_url=f"{self.endpoint.rstrip('/')}/v1", 
                api_key="lm-studio"
            )
            
            # Prepare request parameters
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            # Add tools if provided
            if tools:
                print(f"   🛠️  Adding {len(tools)} tools to LM Studio request")
                request_params["tools"] = tools
            
            print(f"📨 {self.agent_stage.upper()} LM STUDIO REQUEST:")
            print(f"   🎯 Model: {request_params['model']}")
            print(f"   🗣️  Messages: {len(request_params['messages'])} messages")
            if 'tools' in request_params:
                tool_names = [tool.get('function', {}).get('name', 'unknown') for tool in request_params['tools']]
                print(f"   🛠️  Tools: {tool_names}")
            
            # Make request using OpenAI client
            response = await client.chat.completions.create(**request_params)
            
            # Extract response data
            choice = response.choices[0]
            message_content = choice.message.content or ""
            tool_calls = choice.message.tool_calls or []
            
            print(f"📡 {self.agent_stage.upper()} LM STUDIO RESPONSE:")
            print(f"   ✅ Success! Using OpenAI client with LM Studio")
            print(f"   📝 Content: {len(message_content)} chars")
            print(f"   🔧 Tool calls: {len(tool_calls)}")
            
            # Convert to Ollama-compatible format for the rest of the system
            ollama_tool_calls = []
            if tool_calls:
                for tool_call in tool_calls:
                    ollama_tool_calls.append({
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    })
            
            ollama_response = {
                "message": {
                    "content": message_content,
                    "tool_calls": ollama_tool_calls
                }
            }
            
            return ollama_response
                    
        except Exception as e:
            error_msg = f"LM Studio Python API request failed: {str(e)}"
            print(f"   ❌ Error: {error_msg}")
            return {"error": error_msg}

    async def call_together_api(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Use Together AI API with function calling support"""
        print(f"🟣 {self.agent_stage.upper()} TOGETHER AI API REQUEST:")
        print(f"   Model: {self.model}")
        print(f"   API Key Env: {self.api_key_env}")

        # LOG THE ACTUAL MESSAGES BEING SENT
        print(f"📨 {self.agent_stage.upper()} MESSAGES TO TOGETHER AI:")
        for i, msg in enumerate(messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            print(f"   Message {i+1} ({role}): {len(content)} chars")
            if role == 'system':
                print(f"      System prompt preview: {repr(content[:200])}...")
            elif role == 'user':
                print(f"      User message preview: {repr(content[:300])}...")
                if len(content) > 300:
                    print(f"      User message full: {repr(content)}")
            else:
                print(f"      Content preview: {repr(content[:200])}...")

        try:
            from together import Together
            import os

            # Get API key from environment
            api_key = os.environ.get("TOGETHER_API_KEY")
            if not api_key:
                error_msg = "TOGETHER_API_KEY environment variable not set"
                print(f"   ❌ Error: {error_msg}")
                return {"error": error_msg}

            # Initialize Together client
            client = Together(api_key=api_key)

            # Prepare request parameters
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 3000  # Increased for thinking models like Qwen
            }

            # Add tools if provided
            if tools:
                request_params["tools"] = tools
                print(f"   🔧 Tools provided: {len(tools)}")
                for tool in tools:
                    tool_name = tool.get('function', {}).get('name', 'unknown')
                    print(f"      - {tool_name}")

                # Let all agents choose their tools freely
                # Triage agent has its own JSON parsing mechanism
                print(f"   🆓 Allowing free tool choice for {self.agent_stage} agent")

            print(f"   📤 Making Together API request...")

            # Make the API call with timeout
            import asyncio

            async def make_api_call():
                return client.chat.completions.create(**request_params)

            # Add 30 second timeout
            response = await asyncio.wait_for(make_api_call(), timeout=30.0)

            print(f"   ✅ Together API call successful")

            # Handle tool calls if present
            message = response.choices[0].message
            if hasattr(message, 'tool_calls') and message.tool_calls:
                return await self.handle_together_tool_calls(response, messages, tools)
            else:
                return {
                    "success": True,
                    "content": message.content,
                    "usage": getattr(response, 'usage', {}),
                    "tool_calls": []
                }

        except asyncio.TimeoutError:
            error_msg = "Together AI API request timed out after 30 seconds"
            print(f"   ⏰ Timeout: {error_msg}")
            return {"error": error_msg}
        except ImportError:
            error_msg = "Together library not installed. Run: pip install together"
            print(f"   ❌ Error: {error_msg}")
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Together AI API request failed: {str(e)}"
            print(f"   ❌ Error: {error_msg}")
            return {"error": error_msg}

    async def handle_together_tool_calls(self, response, messages: List[Dict[str, str]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Handle tool calls from Together AI API response"""
        print(f"🔧 {self.agent_stage.upper()} TOGETHER TOOL CALLS:")

        message = response.choices[0].message
        tool_calls = message.tool_calls

        print(f"   🔄 Executing {len(tool_calls)} tool calls...")
        tool_results = []
        tools_used = []

        for i, tool_call in enumerate(tool_calls):
            function_name = tool_call.function.name
            function_args = tool_call.function.arguments

            print(f"   🔧 Tool {i+1}/{len(tool_calls)}: {function_name}")
            print(f"      Args: {function_args}")

            # Execute the tool
            # Convert Together API format to standard tool call format
            # Parse JSON string arguments from Together AI
            try:
                if isinstance(function_args, str):
                    parsed_args = json.loads(function_args)
                elif isinstance(function_args, dict):
                    parsed_args = function_args
                else:
                    parsed_args = {}
            except json.JSONDecodeError as e:
                print(f"      ❌ Failed to parse arguments JSON: {e}")
                parsed_args = {}

            standard_tool_call = {
                "function": {
                    "name": function_name,
                    "arguments": parsed_args
                }
            }
            result = await self.execute_tool_call(standard_tool_call)
            tool_results.append({
                "tool": function_name,
                "result": result
            })
            tools_used.append(function_name)

            if isinstance(result, dict) and "error" in result:
                print(f"      Error: {result['error']}")

        # Debug: Show what content we have from the initial response
        initial_content = message.content or ""
        print(f"   📄 Initial message content: {repr(initial_content[:200])}")

        # DETAILED LOGGING: Show complete response analysis
        print(f"🔍 DETAILED RESPONSE ANALYSIS:")
        print(f"   📏 Content length: {len(initial_content)} chars")
        print(f"   🔧 Tools called: {len(tool_calls)} ({[tc.function.name for tc in tool_calls]})")
        print(f"   🎯 Agent stage: {self.agent_stage}")

        # Show more content if it exists
        if len(initial_content) > 200:
            print(f"   📄 Full content preview: {repr(initial_content[:500])}...")
        elif initial_content:
            print(f"   📄 Full content: {repr(initial_content)}")
        else:
            print(f"   📄 No content in response")

        # Show tool results details
        if tool_results:
            print(f"   🔧 Tool execution results:")
            for i, result in enumerate(tool_results):
                tool_name = tool_calls[i].function.name if i < len(tool_calls) else "unknown"
                print(f"      Tool {i+1} ({tool_name}): {result}")

        # Triage agent has its own process method that handles JSON parsing directly
        # No follow-up call needed - let it handle the response parsing itself
        if True:  # Re-enabled follow-up call for proper tool result handling
            print(f"   🔄 Making follow-up call to get final {self.agent_stage} response...")

            # Prepare messages with tool results
            follow_up_messages = messages.copy()

            # Add the assistant's tool call message
            follow_up_messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    } for i, tool_call in enumerate(tool_calls)
                ]
            })

            # Add tool results as tool messages
            for i, (tool_call, result) in enumerate(zip(tool_calls, tool_results)):
                follow_up_messages.append({
                    "role": "tool",
                    "tool_call_id": f"call_{i}",
                    "content": str(result.get("result", result))
                })

            try:
                # Make follow-up call without tools to get final response
                from together import Together
                import os
                client = Together(api_key=os.environ.get("TOGETHER_API_KEY"))

                # For triage agent, use JSON schema enforcement
                if self.agent_stage == "triage":
                    from agents.triage_agent import TriageResponse

                    follow_up_response = client.chat.completions.create(
                        model=self.model,
                        messages=follow_up_messages,
                        temperature=0.7,
                        max_tokens=3000,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {
                                "name": "triage_response",
                                "schema": TriageResponse.get_json_schema()
                            }
                        }
                    )
                    print(f"   🎯 Using JSON schema enforcement for triage response")
                else:
                    # Add explicit instruction for final response
                    follow_up_messages.append({
                        "role": "user",
                        "content": "Now provide your final analysis and conclusions based on the tool results above. Do not call any more tools - just provide your written response."
                    })

                    follow_up_response = client.chat.completions.create(
                        model=self.model,
                        messages=follow_up_messages,
                        temperature=0.7,
                        max_tokens=3000
                    )

                final_content = follow_up_response.choices[0].message.content
                print(f"   ✅ Follow-up response received: {repr(final_content[:200])}")

                # Check if database write tool was called
                database_writes = [t for t in tools_used if 'write_to_database' in t or 'database' in t]
                if not database_writes and self.agent_stage == "research" and hasattr(self, '_current_post_id'):
                    print(f"   🔧 FOLLOW-UP FALLBACK: Auto-calling write_to_database for research agent")

                    # Analyze what happened with the searches
                    search_failures = [result for result in tool_results if isinstance(result, dict) and "error" in result]
                    search_successes = [result for result in tool_results if isinstance(result, dict) and "success" in result and result["success"]]

                    # Create fallback database write
                    fallback_tool_call = {
                        "function": {
                            "name": "write_to_database",
                            "arguments": {
                                "post_id": self._current_post_id,
                                "stage": "research",
                                "content": {
                                    "result": f"Research analysis completed: {final_content[:500]}",
                                    "search_failures": len(search_failures),
                                    "search_successes": len(search_successes),
                                    "search_errors": [f"Search failed: {result.get('error', 'Unknown error')}" for result in search_failures],
                                    "fact_check_status": "limited_research" if search_failures else "research_completed",
                                    "confidence": 0.3 if search_failures else 0.7,
                                    "note": "Fallback database write after follow-up response"
                                },
                                "next_stage": "response"
                            }
                        }
                    }

                    try:
                        fallback_result = await self.execute_tool_call(fallback_tool_call)
                        tool_results.append({
                            "tool": "write_to_database",
                            "result": fallback_result
                        })
                        tools_used.append("write_to_database")
                        print(f"   ✅ FOLLOW-UP FALLBACK SUCCESSFUL: Database write executed")
                    except Exception as e:
                        print(f"   ❌ FOLLOW-UP FALLBACK FAILED: {e}")

                return {
                    "success": True,
                    "content": final_content,
                    "usage": getattr(follow_up_response, 'usage', {}),
                    "tool_calls": tool_results,
                    "tools_used": tools_used
                }

            except Exception as e:
                print(f"   ❌ Follow-up call failed: {e}")
                # Fall back to original content
                pass

        # FINAL DECISION LOGGING
        final_content = message.content or f"Executed {len(tool_calls)} tools: {', '.join(tools_used)}"
        print(f"🎯 RESPONSE HANDLER FINAL DECISION:")
        print(f"   📝 Returning content: {len(final_content)} chars")
        print(f"   🔧 Tool calls executed: {len(tool_results)}")
        print(f"   📊 Usage info: {getattr(response, 'usage', {})}")

        # Show content being returned
        if message.content:
            print(f"   📄 Original content: {repr(message.content[:300])}")
        else:
            print(f"   📄 Generated content: {repr(final_content[:300])}")

        # Analyze if this is expected behavior
        if not tool_results and not message.content:
            print(f"   🚨 ERROR: No tool calls AND no content - this is problematic!")
        elif tool_results and not message.content:
            print(f"   ⚠️  WARNING: Tools executed but no original content - may be incomplete!")

        # Check if database write tool was called
        database_writes = [t for t in tools_used if 'write_to_database' in t or 'database' in t]
        if database_writes:
            print(f"   ✅ Database write tools called: {database_writes}")
        else:
            print(f"   ❌ NO DATABASE WRITE TOOL CALLED - Post will NOT advance!")

            # FALLBACK: For research agents, automatically call write_to_database if missing
            if self.agent_stage == "research" and hasattr(self, '_current_post_id'):
                print(f"   🔧 FALLBACK: Auto-calling write_to_database for research agent")

                # Analyze what happened with the searches
                search_failures = [result for result in tool_results if isinstance(result, dict) and "error" in result]
                search_successes = [result for result in tool_results if isinstance(result, dict) and "success" in result and result["success"]]

                # Create fallback database write
                fallback_tool_call = {
                    "function": {
                        "name": "write_to_database",
                        "arguments": {
                            "post_id": self._current_post_id,
                            "stage": "research",
                            "content": {
                                "result": "Research completed with search limitations",
                                "search_failures": len(search_failures),
                                "search_successes": len(search_successes),
                                "search_errors": [f"Search failed: {result.get('error', 'Unknown error')}" for result in search_failures],
                                "fact_check_status": "limited_research" if search_failures else "research_completed",
                                "confidence": 0.3 if search_failures else 0.7,
                                "note": "Fallback database write due to incomplete tool execution"
                            },
                            "next_stage": "response"
                        }
                    }
                }

                try:
                    fallback_result = await self.execute_tool_call(fallback_tool_call)
                    tool_results.append({
                        "tool": "write_to_database",
                        "result": fallback_result
                    })
                    tools_used.append("write_to_database")
                    print(f"   ✅ FALLBACK SUCCESSFUL: Database write executed")
                    print(f"   📝 Fallback result: {fallback_result}")

                    # Record fallback event to database
                    await self._record_fallback_event(
                        post_id=self._current_post_id,
                        stage="research",
                        reason="Missing database write after search failures/rate limits",
                        search_failures=len(search_failures),
                        search_successes=len(search_successes),
                        error_details={
                            "search_errors": [f"Search failed: {result.get('error', 'Unknown error')}" for result in search_failures],
                            "tool_results_count": len(tool_results),
                            "original_content_present": bool(message.content)
                        }
                    )

                except Exception as e:
                    print(f"   ❌ FALLBACK FAILED: {e}")

        return {
            "success": True,
            "content": final_content,
            "usage": getattr(response, 'usage', {}),
            "tool_calls": tool_results,
            "tools_used": tools_used
        }

    async def call_ollama_python_api(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Use native Ollama Python API"""
        print(f"🟠 {self.agent_stage.upper()} OLLAMA PYTHON API REQUEST:")
        print(f"   Model: {self.model}")
        print(f"   Endpoint: {self.endpoint}")
        
        try:
            import ollama
            
            # Prepare request parameters using native Ollama format
            request_params = {
                "model": self.model,
                "messages": messages
            }
            
            # Add tools if provided using native Ollama format
            if tools:
                print(f"   🛠️  Adding {len(tools)} tools to Ollama request")
                request_params["tools"] = tools
            
            print(f"📨 {self.agent_stage.upper()} OLLAMA REQUEST:")
            print(f"   🎯 Model: {request_params['model']}")
            print(f"   🗣️  Messages: {len(request_params['messages'])} messages")
            if 'tools' in request_params:
                tool_names = [tool.get('function', {}).get('name', 'unknown') for tool in request_params['tools']]
                print(f"   🛠️  Tools: {tool_names}")
            
            # Make request using native Ollama API
            if self.endpoint == "http://localhost:11434" or self.endpoint == "localhost:11434":
                # Default Ollama endpoint
                client = ollama.AsyncClient()
                response = await client.chat(**request_params)
            else:
                # Custom Ollama endpoint (including other IPs/ports)
                client = ollama.AsyncClient(host=self.endpoint)
                response = await client.chat(**request_params)
            
            print(f"📡 {self.agent_stage.upper()} OLLAMA RESPONSE:")
            print(f"   ✅ Success! Using native Ollama Python API")
            
            # Extract response data
            message = response.get("message", {})
            message_content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])
            
            print(f"   📝 Content: {len(message_content)} chars")
            print(f"   🔧 Tool calls: {len(tool_calls)}")
            
            # Return in consistent format
            return {
                "message": {
                    "content": message_content,
                    "tool_calls": tool_calls
                }
            }
                    
        except Exception as e:
            error_msg = f"Ollama Python API request failed: {str(e)}"
            print(f"   ❌ Error: {error_msg}")
            return {"error": error_msg}
    
    async def execute_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call and return the result"""
        function_name = tool_call.get("function", {}).get("name")
        function_args = tool_call.get("function", {}).get("arguments", {})
        
        print(f"🔧 {self.agent_stage.upper()} TOOL EXECUTION:")
        print(f"   Tool: {function_name}")
        
        
        if function_name not in self.tool_implementations:
            error = f"Tool '{function_name}' not implemented"
            print(f"   ❌ Error: {error}")
            return {"error": error}
        
        try:
            # Parse arguments if they're a string
            if isinstance(function_args, str):
                function_args = json.loads(function_args)
            
            print(f"   📝 Arguments: {list(function_args.keys()) if isinstance(function_args, dict) else type(function_args)}")
            
            
            tool_func = self.tool_implementations[function_name]
            result = await tool_func(**function_args)
            
            if isinstance(result, dict) and result.get("success"):
                print(f"   ✅ Tool success: {function_name}")
                if function_name == "write_to_database":
                    next_stage = result.get("next_stage")
                    post_id = result.get("post_id") 
                    print(f"      📊 Database write: Post {post_id} → {next_stage}")
            else:
                print(f"   ❌ Tool failed: {function_name}")
                if isinstance(result, dict) and "error" in result:
                    print(f"      Error: {result['error']}")
            
            return result
            
        except json.JSONDecodeError as e:
            error = f"Invalid JSON in tool arguments: {str(e)}"
            print(f"   🔧 JSON Error: {error}")
            return {"error": error}
        except Exception as e:
            error = f"Tool execution failed: {str(e)}"
            print(f"   💥 Tool Exception: {error}")
            return {"error": error}
    
    async def handle_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the response from Ollama, including tool calls"""
        print(f"🎯 {self.agent_stage.upper()} RESPONSE HANDLER:")
        
        if "error" in response:
            print(f"   ❌ Error in response: {response['error']}")
            
                    
            return response
        
        message = response.get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")
        
        print(f"   📝 Content: {len(content)} chars")
        print(f"   🔧 Tool calls: {len(tool_calls)}")
        
        
        # If no tool calls, return the text response
        if not tool_calls:
            print(f"   📄 No tools called, returning text response")
            
                
            return {
                "success": True,
                "content": content,
                "usage": response.get("usage", {}),
                "tool_calls": []
            }
        
        # Execute tool calls
        print(f"   🔄 Executing {len(tool_calls)} tool calls...")
        tool_results = []
        for i, tool_call in enumerate(tool_calls):
            tool_name = tool_call.get("function", {}).get("name", "unknown")
            print(f"   🔧 Executing tool {i+1}/{len(tool_calls)}: {tool_name}")
            
            result = await self.execute_tool_call(tool_call)
            tool_results.append({
                "tool": tool_name,
                "result": result
            })
            
            if isinstance(result, dict) and result.get("success"):
                print(f"   ✅ Tool {tool_name} completed successfully")
            else:
                print(f"   ❌ Tool {tool_name} failed")
        
        print(f"   🏁 All tools executed, returning results")
        
        
        return {
            "success": True,
            "content": content,
            "tool_calls": tool_results,
            "usage": response.get("usage", {})
        }
    
    async def process(self, post_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Main processing method for the agent"""
        try:
            # Track current post_id for fallback database writes
            self._current_post_id = post_data.get('id')

            # Build messages for this processing stage
            messages = self.build_messages(post_data, context)

            # Call LLM with tools
            response = await self.call_llm(messages, self.tools)

            # Check if response was already processed (Together AI with tool calls)
            if "tool_calls" in response and response.get("success") is not None:
                # Already processed by handle_together_tool_calls
                return response
            else:
                # Need to handle response (Ollama/LM Studio)
                result = await self.handle_response(response)
                return result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Agent processing failed: {str(e)}"
            }
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Return information about this agent"""
        return {
            "model": self.model,
            "endpoint": self.endpoint,
            "timeout": self.timeout,
            "tools": [tool["function"]["name"] for tool in self.tools],
            "system_prompt_preview": self.get_system_prompt()[:200] + "..."
        }


class MockAgent(BaseAgent):
    """Mock agent for testing without actual LLM calls"""
    
    def __init__(self, agent_type: str):
        super().__init__("mock-model", "http://localhost:8000")
        self.agent_type = agent_type
    
    def get_tools(self) -> List[Dict[str, Any]]:
        return [DatabaseWriteTool.get_tool_definition()]
    
    def get_default_system_prompt(self) -> str:
        return f"Mock {self.agent_type} agent for testing"
    
    def build_messages(self, post_data: dict, context: dict = None) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": f"Process post: {post_data.get('title', 'No title')}"}
        ]
    
    async def call_llm(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return mock response"""
        return {
            "message": {
                "content": f"Mock {self.agent_type} response for: {messages[-1]['content'][:50]}...",
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_to_database",
                            "arguments": {
                                "post_id": 1,
                                "stage": self.agent_type,
                                "content": {
                                    "result": f"Mock {self.agent_type} result",
                                    "confidence": 0.9
                                },
                                "next_stage": "research" if self.agent_type == "triage" else None
                            }
                        }
                    }
                ] if self.agent_type in ["triage", "research", "response", "editorial"] else []
            },
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}
        }