"""
Brave Search Tool for Research Agent
Uses Brave Search API to find information about factual claims
"""
import os
import json
import httpx
from typing import Dict, Any, Optional


class BraveSearchTool:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("BRAVE_API_KEY")
        if not self.api_key:
            raise ValueError("BRAVE_API_KEY environment variable is required")
    
    @staticmethod
    def get_tool_definition() -> Dict[str, Any]:
        """Return the Ollama tool definition for Brave Search"""
        return {
            "type": "function",
            "function": {
                "name": "brave_web_search",
                "description": "Search the web using Brave Search API to find information about claims and topics",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to find relevant information"
                        },
                        "count": {
                            "type": "integer",
                            "description": "Number of search results to return (1-20)",
                            "default": 10
                        },
                        "search_lang": {
                            "type": "string", 
                            "description": "Search language code (e.g., 'en')",
                            "default": "en"
                        },
                        "country": {
                            "type": "string",
                            "description": "Country code for search results (e.g., 'US')", 
                            "default": "US"
                        },
                        "safesearch": {
                            "type": "string",
                            "description": "Safe search setting: off, moderate, strict",
                            "default": "moderate"
                        },
                        "freshness": {
                            "type": "string",
                            "description": "Time filter: pd (past day), pw (past week), pm (past month), py (past year)",
                            "default": None
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute Brave Search API call"""
        query = kwargs.get("query")
        if not query:
            return {"error": "Query parameter is required"}
        
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key
        }
        
        params = {
            "q": query,
            "count": min(kwargs.get("count", 10), 20),  # Cap at 20
            "search_lang": kwargs.get("search_lang", "en"),
            "country": kwargs.get("country", "US"),
            "safesearch": kwargs.get("safesearch", "moderate")
        }
        
        # Add freshness filter if specified
        if kwargs.get("freshness"):
            params["freshness"] = kwargs["freshness"]
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers=headers,
                    params=params
                )
                
            if response.status_code != 200:
                return {
                    "error": f"Search failed with status {response.status_code}: {response.text}",
                    "query": query
                }
                
            data = response.json()
            
            # Process and format search results
            results = []
            web_results = data.get("web", {}).get("results", [])
            
            for result in web_results:
                formatted_result = {
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "description": result.get("description", ""),
                    "published": result.get("age", ""),
                    "snippet": result.get("extra_snippets", [])
                }
                results.append(formatted_result)
            
            # Include news results if available
            news_results = []
            for news in data.get("news", {}).get("results", [])[:3]:  # Limit to 3 news items
                news_results.append({
                    "title": news.get("title", ""),
                    "url": news.get("url", ""),
                    "description": news.get("description", ""),
                    "published": news.get("age", ""),
                    "source": news.get("meta_url", {}).get("netloc", "")
                })
            
            return {
                "success": True,
                "query": query,
                "web_results": results,
                "news_results": news_results,
                "total_results": len(results),
                "search_metadata": {
                    "country": params["country"],
                    "language": params["search_lang"],
                    "safesearch": params["safesearch"]
                }
            }
            
        except httpx.TimeoutException:
            return {
                "error": "Search request timed out",
                "query": query
            }
        except httpx.RequestError as e:
            return {
                "error": f"Search request failed: {str(e)}",
                "query": query
            }
        except json.JSONDecodeError:
            return {
                "error": "Invalid JSON response from search API",
                "query": query
            }
        except Exception as e:
            return {
                "error": f"Unexpected error: {str(e)}",
                "query": query
            }


# Tool function for direct use in agent implementations
async def brave_web_search(**kwargs) -> Dict[str, Any]:
    """Direct function interface for Brave Search tool"""
    tool = BraveSearchTool()
    return await tool.execute(**kwargs)


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_search():
        tool = BraveSearchTool()
        
        # Test search
        result = await tool.execute(
            query="climate change latest research 2024",
            count=5,
            freshness="pm"  # Past month
        )
        
        print(json.dumps(result, indent=2))
    
    # Run test if API key is available
    if os.getenv("BRAVE_API_KEY"):
        asyncio.run(test_search())
    else:
        print("Set BRAVE_API_KEY environment variable to test")
        print("Tool definition:", json.dumps(BraveSearchTool.get_tool_definition(), indent=2))