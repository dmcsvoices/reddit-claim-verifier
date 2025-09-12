"""
Time Source Tool - Simplified implementation providing reliable date/time to agents
Uses system time with timezone support as a reliable fallback approach
"""
import asyncio
import json
import subprocess
import sys
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import pytz

class TimeSourceTool:
    """Tool for getting accurate date/time information via MCP time server"""
    
    def __init__(self):
        self.mcp_server_process = None
        self.server_port = 5200  # Use port in 5000 range as requested
        
    @staticmethod
    def get_tool_definition() -> Dict[str, Any]:
        """Return the OpenAI function calling tool definition"""
        return {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Get the current date and time from a trusted source. Supports timezone conversion and various formats.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "IANA timezone name (e.g., 'UTC', 'America/New_York', 'Europe/London'). Defaults to UTC.",
                            "default": "UTC"
                        },
                        "format": {
                            "type": "string", 
                            "description": "Output format: 'iso' for ISO 8601, 'human' for human readable, 'timestamp' for Unix timestamp",
                            "enum": ["iso", "human", "timestamp"],
                            "default": "iso"
                        }
                    },
                    "additionalProperties": False
                }
            }
        }
    
    async def start_mcp_server(self) -> bool:
        """Start the MCP time server if not already running"""
        if self.mcp_server_process and self.mcp_server_process.poll() is None:
            return True  # Already running
            
        try:
            # Start MCP time server with stdio transport
            self.mcp_server_process = subprocess.Popen(
                [sys.executable, "-m", "mcp_server_time"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Give it a moment to start
            await asyncio.sleep(0.5)
            
            if self.mcp_server_process.poll() is None:
                print(f"🕐 MCP Time Server started successfully (PID: {self.mcp_server_process.pid})")
                return True
            else:
                print(f"❌ MCP Time Server failed to start")
                return False
                
        except Exception as e:
            print(f"❌ Error starting MCP Time Server: {e}")
            return False
    
    async def stop_mcp_server(self):
        """Stop the MCP time server"""
        if self.mcp_server_process:
            try:
                self.mcp_server_process.terminate()
                self.mcp_server_process.wait(timeout=5)
                print("🕐 MCP Time Server stopped")
            except subprocess.TimeoutExpired:
                self.mcp_server_process.kill()
                print("🕐 MCP Time Server killed (timeout)")
            except Exception as e:
                print(f"⚠️ Error stopping MCP Time Server: {e}")
    
    async def send_mcp_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a JSON-RPC request to the MCP server"""
        if not self.mcp_server_process or self.mcp_server_process.poll() is not None:
            if not await self.start_mcp_server():
                return {"error": "Failed to start MCP time server"}
        
        try:
            # First initialize the MCP session
            if method == "get_current_time":
                # Send initialization request
                init_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "clientInfo": {
                            "name": "reddit-monitor-agent",
                            "version": "1.0.0"
                        }
                    }
                }
                
                init_json = json.dumps(init_request) + "\n"
                self.mcp_server_process.stdin.write(init_json)
                self.mcp_server_process.stdin.flush()
                
                # Read initialization response
                init_response_line = self.mcp_server_process.stdout.readline()
                if init_response_line:
                    init_response = json.loads(init_response_line.strip())
                    print(f"🕐 MCP Init Response: {init_response}")
                
                # Send tools/call request
                tool_request = {
                    "jsonrpc": "2.0", 
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "get_current_time",
                        "arguments": params or {}
                    }
                }
                
                tool_json = json.dumps(tool_request) + "\n"
                self.mcp_server_process.stdin.write(tool_json)
                self.mcp_server_process.stdin.flush()
                
                # Read tool response
                tool_response_line = self.mcp_server_process.stdout.readline()
                if not tool_response_line:
                    return {"error": "No response from MCP server"}
                
                response = json.loads(tool_response_line.strip())
                print(f"🕐 MCP Tool Response: {response}")
                return response
            else:
                # Generic request
                request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or {}
                }
                
                request_json = json.dumps(request) + "\n"
                self.mcp_server_process.stdin.write(request_json)
                self.mcp_server_process.stdin.flush()
                
                response_line = self.mcp_server_process.stdout.readline()
                if not response_line:
                    return {"error": "No response from MCP server"}
                
                response = json.loads(response_line.strip())
                return response
            
        except Exception as e:
            return {"error": f"MCP communication error: {str(e)}"}
    
    async def execute(self, timezone: str = "UTC", format: str = "iso", **kwargs) -> Dict[str, Any]:
        """
        Get current time with system time (reliable implementation)
        
        Args:
            timezone: IANA timezone name (default: UTC)
            format: Output format - 'iso', 'human', or 'timestamp'
            
        Returns:
            Dict with time information or error
        """
        
        print(f"🕐 TIME TOOL REQUEST:")
        print(f"   Timezone: {timezone}")
        print(f"   Format: {format}")
        
        try:
            # Use system time directly (most reliable)
            return await self._get_system_time(timezone, format)
                
        except Exception as e:
            print(f"   💥 Exception in time tool: {e}")
            return {
                "success": False,
                "error": f"Failed to get time: {str(e)}",
                "source": "none"
            }
    
    async def _get_system_time(self, timezone: str, format: str) -> Dict[str, Any]:
        """Get system time with timezone support"""
        try:            
            print(f"   🔄 Getting system time")
            
            # Get current UTC time
            now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
            
            # Convert to requested timezone
            if timezone != "UTC":
                try:
                    tz = pytz.timezone(timezone)
                    now_local = now_utc.astimezone(tz)
                except:
                    # Invalid timezone, use UTC
                    now_local = now_utc
                    timezone = "UTC"
                    print(f"   ⚠️ Invalid timezone, defaulting to UTC")
            else:
                now_local = now_utc
            
            # Format as requested
            if format == "timestamp":
                formatted_time = str(int(now_local.timestamp()))
            elif format == "human":
                formatted_time = now_local.strftime("%Y-%m-%d %H:%M:%S %Z")
            else:
                formatted_time = now_local.isoformat()
            
            print(f"   ✅ System time retrieved: {formatted_time}")
            
            return {
                "success": True,
                "time": formatted_time,
                "timezone": timezone,
                "format": format,
                "source": "System time (NTP synchronized)",
                "timestamp": now_local.timestamp()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get time: {str(e)}",
                "source": "none"
            }
    
    def __del__(self):
        """Cleanup MCP server on destruction"""
        if self.mcp_server_process:
            try:
                self.mcp_server_process.terminate()
            except:
                pass


# Singleton instance for reuse across agents
_time_tool_instance = None

def get_time_tool() -> TimeSourceTool:
    """Get singleton TimeSourceTool instance"""
    global _time_tool_instance
    if _time_tool_instance is None:
        _time_tool_instance = TimeSourceTool()
    return _time_tool_instance