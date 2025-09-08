"""
Base Agent class for LLM agents with Ollama tool support
"""
import json
import httpx
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from ..tools.database_write import DatabaseWriteTool
from ..tools.brave_search import BraveSearchTool


class BaseAgent(ABC):
    def __init__(self, model: str, endpoint: str, timeout: int = 60):
        self.model = model
        self.endpoint = endpoint.rstrip('/')
        self.timeout = timeout
        self.tools = self.get_tools()
        self.tool_implementations = self.get_tool_implementations()
    
    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of tool definitions for this agent"""
        pass
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent"""
        pass
    
    @abstractmethod
    def build_messages(self, post_data: dict, context: dict = None) -> List[Dict[str, str]]:
        """Build the message array for the LLM request"""
        pass
    
    def get_tool_implementations(self) -> Dict[str, Any]:
        """Return mapping of tool names to their implementation functions"""
        implementations = {
            "write_to_database": DatabaseWriteTool().execute
        }
        
        # Add Brave Search if this agent uses it
        for tool in self.tools:
            if tool["function"]["name"] == "brave_web_search":
                implementations["brave_web_search"] = BraveSearchTool().execute
                break
        
        return implementations
    
    async def call_ollama(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a request to Ollama with tool support"""
        request_data = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        
        if tools:
            request_data["tools"] = tools
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.endpoint}/api/chat",
                    json=request_data
                )
                
            if response.status_code != 200:
                return {
                    "error": f"Ollama request failed: {response.status_code} - {response.text}"
                }
            
            return response.json()
            
        except httpx.TimeoutException:
            return {"error": f"Request timed out after {self.timeout} seconds"}
        except httpx.RequestError as e:
            return {"error": f"Request error: {str(e)}"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response from Ollama"}
        except Exception as e:
            return {"error": f"Unexpected error: {str(e)}"}
    
    async def execute_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call and return the result"""
        function_name = tool_call.get("function", {}).get("name")
        function_args = tool_call.get("function", {}).get("arguments", {})
        
        if function_name not in self.tool_implementations:
            return {"error": f"Tool '{function_name}' not implemented"}
        
        try:
            # Parse arguments if they're a string
            if isinstance(function_args, str):
                function_args = json.loads(function_args)
            
            tool_func = self.tool_implementations[function_name]
            result = await tool_func(**function_args)
            
            return result
            
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON in tool arguments: {str(e)}"}
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}
    
    async def handle_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the response from Ollama, including tool calls"""
        if "error" in response:
            return response
        
        message = response.get("message", {})
        tool_calls = message.get("tool_calls", [])
        
        # If no tool calls, return the text response
        if not tool_calls:
            return {
                "success": True,
                "content": message.get("content", ""),
                "usage": response.get("usage", {}),
                "tool_calls": []
            }
        
        # Execute tool calls
        tool_results = []
        for tool_call in tool_calls:
            result = await self.execute_tool_call(tool_call)
            tool_results.append({
                "tool": tool_call.get("function", {}).get("name"),
                "result": result
            })
        
        return {
            "success": True,
            "content": message.get("content", ""),
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
    
    def get_system_prompt(self) -> str:
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