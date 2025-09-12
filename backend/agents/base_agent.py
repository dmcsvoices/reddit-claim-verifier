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
    def __init__(self, model: str, endpoint: str, timeout: int = 60):
        self.model = model
        self.endpoint = endpoint.rstrip('/')
        self.timeout = timeout
        # Determine agent stage from class name (e.g., "TriageAgent" -> "triage")
        self.agent_stage = self.__class__.__name__.lower().replace('agent', '')
        self.tools = self.get_tools()
        self.tool_implementations = self.get_tool_implementations()
    
    def _get_db_connection(self):
        """Get database connection"""
        return psycopg.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5443"),
            dbname=os.getenv("DB_NAME", "redditmon"),
            user=os.getenv("DB_USER", "redditmon"),
            password=os.getenv("DB_PASSWORD", "supersecret")
        )
    
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
            print(f"Warning: Could not fetch system prompt from database for {self.agent_stage}: {e}")
            try:
                if conn:
                    conn.close()
            except:
                pass
        
        # Fallback to default prompt
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
    
    async def call_ollama(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a request to Ollama using Python library for proper tool support"""
        print(f"🌐 {self.agent_stage.upper()} API REQUEST:")
        print(f"   Model: {self.model}")
        print(f"   Endpoint: {self.endpoint}")
        print(f"   Tools available: {len(tools) if tools else 0}")
        if tools:
            tool_names = [tool.get('function', {}).get('name', 'unknown') for tool in tools]
            print(f"   Tool names: {tool_names}")
        
        # Check if endpoint uses port 1234 (OpenAI-compatible) vs 11434 (Ollama)
        if ":1234" in self.endpoint:
            print(f"   🔄 Port 1234 detected - using OpenAI-compatible format")
            return await self.call_openai_compatible(messages, tools)
        
        try:
            # Configure Ollama client to use custom host if needed
            if self.endpoint != "http://localhost:11434":
                # Extract host from endpoint (remove /api/chat if present)
                host = self.endpoint.replace('/api/chat', '').replace('/v1', '')
                client = ollama.AsyncClient(host=host)
            else:
                client = ollama.AsyncClient()
            
            # Prepare request data
            request_data = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_ctx": 4096,  # Context length
                    "temperature": 0.7
                }
            }
            
            if tools:
                request_data["tools"] = tools
            
            # LOG THE FULL REQUEST BEING SENT TO LLM
            print(f"📨 {self.agent_stage.upper()} LLM REQUEST PAYLOAD:")
            print(f"   🎯 Model: {request_data['model']}")
            print(f"   🗣️  Messages ({len(request_data['messages'])} messages):")
            for i, msg in enumerate(request_data['messages']):
                content_preview = msg.get('content', '')[:300]
                print(f"      {i+1}. Role: {msg.get('role', 'unknown')}")
                print(f"         Content: {content_preview}{'...' if len(msg.get('content', '')) > 300 else ''}")
            if 'tools' in request_data:
                print(f"   🛠️  Tools: {[t.get('function', {}).get('name', 'unknown') for t in request_data['tools']]}")
            if 'options' in request_data:
                print(f"   ⚙️  Options: {request_data['options']}")
            print(f"   📋 Full Request JSON:")
            print(f"   {json.dumps(request_data, indent=4)}")
            print(f"📨 END REQUEST PAYLOAD")
            
            # Make the request using Python Ollama library
            result = await client.chat(**request_data)
            
            print(f"📡 {self.agent_stage.upper()} API RESPONSE:")
            print(f"   ✅ Success! Using Python Ollama library")
            
            # Log response details
            message = result.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])
            
            print(f"   📝 Content: {len(content)} chars")
            if tool_calls:
                print(f"   🔧 Tool calls: {len(tool_calls)}")
                for i, tool_call in enumerate(tool_calls):
                    func_name = tool_call.get("function", {}).get("name", "unknown")
                    print(f"      {i+1}. {func_name}")
            else:
                print(f"   📝 No tool calls in response")
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ Ollama API failed: {error_msg}")
            
            # If it's an "Unexpected endpoint" error, try OpenAI-compatible format
            if ("Unexpected endpoint" in error_msg or 
                "POST /api/chat" in error_msg or 
                "method. (POST /api/chat)" in error_msg):
                print(f"   🔄 Attempting OpenAI-compatible API format...")
                return await self.call_openai_compatible(messages, tools)
            else:
                error = f"Ollama request failed: {error_msg}"
                print(f"   ❌ Final Error: {error}")
                return {"error": error}
    
    async def call_openai_compatible(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Use OpenAI Python client for LM Studio with proper model loading and tool support"""
        print(f"🌐 {self.agent_stage.upper()} OPENAI-COMPATIBLE API REQUEST:")
        print(f"   Model: {self.model}")
        print(f"   Endpoint: {self.endpoint}")
        
        try:
            # Import OpenAI client
            from openai import AsyncOpenAI
            import httpx
            
            # Create OpenAI client pointing to LM Studio
            client = AsyncOpenAI(
                base_url=f"{self.endpoint.rstrip('/')}/v1",
                api_key="lm-studio"  # LM Studio doesn't require real API key
            )
            
            # Check if model is loaded using direct HTTP request (since OpenAI client doesn't have load API)
            try:
                # Get currently loaded models
                loaded_models = await client.models.list()
                loaded_model_ids = [model.id for model in loaded_models.data]
                print(f"   📋 Currently loaded models: {loaded_model_ids}")
                
                if self.model not in loaded_model_ids:
                    print(f"   🔄 Model {self.model} not loaded, attempting to load via lms command...")
                    # Use lms load command as recommended by LM Studio
                    try:
                        result = subprocess.run(
                            ["lms", "load", self.model],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        if result.returncode == 0:
                            print(f"   ✅ Successfully loaded model: {self.model}")
                            print(f"   📄 lms output: {result.stdout.strip()}")
                            # Wait for model to fully initialize after loading
                            print(f"   ⏳ Waiting 60 seconds for model initialization...")
                            await asyncio.sleep(60)
                        else:
                            print(f"   ⚠️  lms load command failed (exit code {result.returncode})")
                            print(f"   📄 stdout: {result.stdout}")
                            print(f"   📄 stderr: {result.stderr}")
                    except FileNotFoundError:
                        print(f"   ⚠️  lms command not found - install LM Studio CLI tools")
                        print(f"   🔄 Proceeding with request anyway (model might auto-load)")
                    except subprocess.TimeoutExpired:
                        print(f"   ⚠️  lms load command timed out after 30 seconds")
                        print(f"   🔄 Proceeding with request anyway (model might auto-load)")
                    except Exception as load_error:
                        print(f"   ⚠️  Could not load model {self.model}: {load_error}")
                        print(f"   🔄 Proceeding with request anyway (model might auto-load)")
                else:
                    print(f"   ✅ Model {self.model} already loaded")
                    
            except Exception as model_check_error:
                print(f"   ⚠️  Could not check/load model: {model_check_error}")
                print(f"   🔄 Proceeding with request anyway")
            
            # Prepare request parameters
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            # Add tools if provided - LM Studio supports OpenAI-compatible tools
            if tools:
                print(f"   🛠️  Adding {len(tools)} tools to LM Studio request")
                request_params["tools"] = tools
                request_params["tool_choice"] = "auto"  # Let the model decide when to use tools
            
            # Make request using OpenAI client
            completion = await client.chat.completions.create(**request_params)
            
            # Extract response
            choice = completion.choices[0]
            message_content = choice.message.content or ""
            tool_calls = choice.message.tool_calls or []
            
            print(f"📡 {self.agent_stage.upper()} OPENAI-COMPATIBLE RESPONSE:")
            print(f"   ✅ Success! Using OpenAI Python client with LM Studio")
            print(f"   📝 Content: {len(message_content)} chars")
            print(f"   🔧 Tool calls: {len(tool_calls)}")
            
            # SPECIAL DEBUG - Show raw LM Studio response
            print(f"🚨 LM STUDIO RAW RESPONSE DEBUG:")
            print(f"   📋 Full completion object: {completion}")
            print(f"   📋 choice.message: {choice.message}")
            print(f"   📄 Raw message_content: '{message_content}' (type: {type(message_content)})")
            print(f"   📄 message_content repr: {repr(message_content)}")
            if tool_calls:
                print(f"   🛠️  Raw tool_calls:")
                for i, tc in enumerate(tool_calls):
                    print(f"      {i+1}. {tc.function.name}: {tc.function.arguments}")
            print(f"🚨 END LM STUDIO RAW DEBUG")
            
            # Convert OpenAI tool calls to Ollama format if present
            ollama_tool_calls = []
            if tool_calls:
                for tool_call in tool_calls:
                    ollama_tool_calls.append({
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    })
            
            # Convert to Ollama-like response format
            ollama_response = {
                "message": {
                    "content": message_content,
                    "tool_calls": ollama_tool_calls
                }
            }
            
            # SPECIAL DEBUG - Show the formatted response we're returning
            print(f"🚨 OLLAMA-FORMAT RESPONSE WE'RE RETURNING:")
            print(f"   📋 ollama_response: {ollama_response}")
            print(f"   📄 message.content: '{ollama_response['message']['content']}' (len: {len(ollama_response['message']['content'])})")
            print(f"   🛠️  message.tool_calls: {len(ollama_response['message']['tool_calls'])} calls")
            
            return ollama_response
                    
        except Exception as e:
            error_msg = f"OpenAI-compatible request failed: {str(e)}"
            print(f"   ❌ Error: {error_msg}")
            return {"error": error_msg}
    
    async def execute_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call and return the result"""
        function_name = tool_call.get("function", {}).get("name")
        function_args = tool_call.get("function", {}).get("arguments", {})
        
        print(f"🔧 {self.agent_stage.upper()} TOOL EXECUTION:")
        print(f"   Tool: {function_name}")
        
        # SPECIAL DEBUG FOR write_to_database
        if function_name == "write_to_database":
            print(f"🚨 WRITE_TO_DATABASE DEBUG - ENTRY:")
            print(f"   📋 Raw function_args type: {type(function_args)}")
            print(f"   📋 Raw function_args content: {function_args}")
        
        if function_name not in self.tool_implementations:
            error = f"Tool '{function_name}' not implemented"
            print(f"   ❌ Error: {error}")
            return {"error": error}
        
        try:
            # Parse arguments if they're a string
            if isinstance(function_args, str):
                print(f"🚨 PARSING JSON STRING: {function_args}")
                function_args = json.loads(function_args)
                print(f"🚨 PARSED TO: {function_args}")
            
            print(f"   📝 Arguments: {list(function_args.keys()) if isinstance(function_args, dict) else type(function_args)}")
            
            # SPECIAL DEBUG FOR write_to_database - Show all parameters
            if function_name == "write_to_database":
                print(f"🚨 WRITE_TO_DATABASE DEBUG - PARSED ARGS:")
                for key, value in function_args.items():
                    if key == "content":
                        print(f"   🗂️  {key}: {type(value)} - {str(value)[:200]}...")
                    else:
                        print(f"   📝 {key}: {value}")
            
            tool_func = self.tool_implementations[function_name]
            print(f"🚨 CALLING TOOL FUNCTION: {tool_func}")
            result = await tool_func(**function_args)
            
            # SPECIAL DEBUG FOR write_to_database - Show result
            if function_name == "write_to_database":
                print(f"🚨 WRITE_TO_DATABASE DEBUG - RESULT:")
                print(f"   📤 Result type: {type(result)}")
                print(f"   📤 Result content: {result}")
            
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
            
            # FORCE DATABASE STORAGE FOR ALL LLM ERRORS (for debugging)
            print(f"🗄️  STORING {self.agent_stage.upper()} ERROR TO DATABASE:")
            try:
                import psycopg
                db_params = {
                    "host": "localhost",
                    "port": 5443,
                    "dbname": "redditmon",
                    "user": "redditmon", 
                    "password": "supersecret"
                }
                with psycopg.connect(**db_params) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS llm_debug_log (
                                id SERIAL PRIMARY KEY,
                                timestamp TIMESTAMP DEFAULT NOW(),
                                agent_stage VARCHAR(50) NOT NULL,
                                model VARCHAR(100),
                                endpoint VARCHAR(200),
                                content TEXT,
                                tool_calls JSONB,
                                success BOOLEAN
                            )
                        """)
                        
                        cur.execute("""
                            INSERT INTO llm_debug_log (agent_stage, model, endpoint, content, tool_calls, success)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (self.agent_stage, self.model, self.endpoint, f"ERROR: {response['error']}", json.dumps([]), False))
                        
                    conn.commit()
                    print(f"   ✅ {self.agent_stage.upper()} error saved to debug table")
            except Exception as e:
                print(f"   ❌ Failed to save {self.agent_stage.upper()} error to debug table: {e}")
                    
            return response
        
        message = response.get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")
        
        print(f"   📝 Content: {len(content)} chars")
        print(f"   🔧 Tool calls: {len(tool_calls)}")
        
        # SPECIAL DEBUG LOGGING FOR RESEARCH AGENT
        if self.agent_stage == "research":
            print(f"🔬 RESEARCH AGENT DETAILED RESPONSE:")
            print(f"   📄 FULL RESPONSE CONTENT (first 500 chars):")
            print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
            if tool_calls:
                print(f"   🛠️  TOOL CALLS DETAILS:")
                for i, tool_call in enumerate(tool_calls):
                    func_name = tool_call.get("function", {}).get("name", "unknown")
                    func_args = tool_call.get("function", {}).get("arguments", {})
                    print(f"      {i+1}. {func_name}: {str(func_args)[:200]}{'...' if len(str(func_args)) > 200 else ''}")
            print(f"   🔬 END RESEARCH DEBUG")
        
        # If no tool calls, return the text response
        if not tool_calls:
            print(f"   📄 No tools called, returning text response")
            
            # FORCE DATABASE STORAGE FOR ALL TEXT-ONLY LLM RESPONSES (for debugging)
            print(f"🗄️  STORING {self.agent_stage.upper()} TEXT RESPONSE TO DATABASE:")
            try:
                import psycopg
                db_params = {
                    "host": "localhost",
                    "port": 5443,
                    "dbname": "redditmon",
                    "user": "redditmon", 
                    "password": "supersecret"
                }
                with psycopg.connect(**db_params) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS llm_debug_log (
                                id SERIAL PRIMARY KEY,
                                timestamp TIMESTAMP DEFAULT NOW(),
                                agent_stage VARCHAR(50) NOT NULL,
                                model VARCHAR(100),
                                endpoint VARCHAR(200),
                                content TEXT,
                                tool_calls JSONB,
                                success BOOLEAN
                            )
                        """)
                        
                        cur.execute("""
                            INSERT INTO llm_debug_log (agent_stage, model, endpoint, content, tool_calls, success)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (self.agent_stage, self.model, self.endpoint, content, json.dumps([]), True))
                        
                    conn.commit()
                    print(f"   ✅ {self.agent_stage.upper()} text response saved to debug table")
            except Exception as e:
                print(f"   ❌ Failed to save {self.agent_stage.upper()} text response to debug table: {e}")
                
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
        
        # FORCE DATABASE STORAGE FOR ALL LLM RESPONSES (for debugging)
        print(f"🗄️  STORING {self.agent_stage.upper()} RESPONSE TO DATABASE:")
        try:
            import psycopg
            from datetime import datetime
            # Database connection parameters
            db_params = {
                "host": "localhost",
                "port": 5443,
                "dbname": "redditmon",
                "user": "redditmon", 
                "password": "supersecret"
            }
            with psycopg.connect(**db_params) as conn:
                with conn.cursor() as cur:
                    # Create universal debug table if it doesn't exist
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS llm_debug_log (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMP DEFAULT NOW(),
                            agent_stage VARCHAR(50) NOT NULL,
                            model VARCHAR(100),
                            endpoint VARCHAR(200),
                            content TEXT,
                            tool_calls JSONB,
                            success BOOLEAN
                        )
                    """)
                    
                    # Insert the response
                    cur.execute("""
                        INSERT INTO llm_debug_log (agent_stage, model, endpoint, content, tool_calls, success)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (self.agent_stage, self.model, self.endpoint, content, json.dumps(tool_results), True))
                    
                conn.commit()
                print(f"   ✅ {self.agent_stage.upper()} response saved to debug table")
        except Exception as e:
            print(f"   ❌ Failed to save {self.agent_stage.upper()} response to debug table: {e}")
        
        return {
            "success": True,
            "content": content,
            "tool_calls": tool_results,
            "usage": response.get("usage", {})
        }
    
    async def process(self, post_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Main processing method for the agent"""
        try:
            # Build messages for this processing stage
            messages = self.build_messages(post_data, context)
            
            # Call Ollama with tools
            response = await self.call_ollama(messages, self.tools)
            
            # Handle response and tool calls
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
    
    async def call_ollama(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
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