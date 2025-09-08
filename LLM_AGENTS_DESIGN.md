# LLM Agents Design with Ollama Tool Support

## Overview

This document outlines the design of specialized LLM agents that will process Reddit posts through the queue system. Each agent uses Ollama's tool support API with custom tools for their specific functions.

## Agent Architecture

### Base Agent Structure
```python
class BaseAgent:
    def __init__(self, model: str, endpoint: str):
        self.model = model
        self.endpoint = endpoint
        self.tools = self.get_tools()
    
    async def process(self, post_data: dict, context: dict = None) -> dict:
        messages = self.build_messages(post_data, context)
        
        response = await self.call_ollama(
            model=self.model,
            messages=messages,
            tools=self.tools
        )
        
        return await self.handle_response(response)
```

## Tool Definitions

### 1. Brave Search Tool (Research Agent)
```python
brave_search_tool = {
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
                }
            },
            "required": ["query"]
        }
    }
}
```

### 2. Database Write Tool (Content Agents)
```python
database_write_tool = {
    "type": "function", 
    "function": {
        "name": "write_to_database",
        "description": "Write processed content to the database queue system",
        "parameters": {
            "type": "object",
            "properties": {
                "post_id": {
                    "type": "integer",
                    "description": "The ID of the Reddit post being processed"
                },
                "stage": {
                    "type": "string", 
                    "description": "Current processing stage",
                    "enum": ["triage", "research", "response", "editorial"]
                },
                "content": {
                    "type": "object",
                    "description": "The content to write to database",
                    "properties": {
                        "result": {
                            "type": "string",
                            "description": "Main result content"
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score (0.0-1.0)"
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Additional metadata for this stage"
                        }
                    },
                    "required": ["result"]
                },
                "next_stage": {
                    "type": "string",
                    "description": "Next stage to advance to, or null to stop processing",
                    "enum": ["research", "response", "editorial", "post_queue", null]
                }
            },
            "required": ["post_id", "stage", "content"]
        }
    }
}
```

## Specialized Agents

### 1. Triage Agent
**Purpose**: Identify posts that make factual claims worth fact-checking
**Model**: llama3.1:8b (fast, cheap)
**Tools**: [database_write_tool]

```python
class TriageAgent(BaseAgent):
    def get_system_prompt(self):
        return """You are a triage agent that identifies Reddit posts making factual claims.

Your job is to:
1. Analyze the post title and content
2. Identify if it contains factual claims that can be verified
3. Extract the main claims
4. Decide if it's worth fact-checking

Criteria for fact-checking:
- Contains specific factual claims
- Not obviously satirical/memes
- Has enough engagement (upvotes/comments)
- Claims are verifiable through research

Use the write_to_database tool to record your analysis."""

    def build_messages(self, post_data: dict, context: dict = None):
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user", 
                "content": f"""
Analyze this Reddit post:

Title: {post_data['title']}
Author: {post_data['author']}
Subreddit: r/{post_data.get('subreddit', 'unknown')}
Content: {post_data.get('body', 'No content')}
URL: {post_data.get('url', '')}
Upvotes: {post_data.get('upvotes', 0)}
Comments: {post_data.get('num_comments', 0)}

Determine if this post contains factual claims worth researching.
"""
            }
        ]
```

### 2. Research Agent  
**Purpose**: Research factual claims using web search
**Model**: llama3.1:70b (capable, slower)
**Tools**: [brave_search_tool, database_write_tool]

```python
class ResearchAgent(BaseAgent):
    def get_system_prompt(self):
        return """You are a research agent that investigates factual claims.

Your job is to:
1. Review the claims identified by the triage agent
2. Use web search to find relevant, credible sources
3. Analyze the evidence for and against each claim
4. Summarize findings with source citations

Research strategy:
- Search for primary sources and authoritative websites
- Look for recent information and contradicting sources
- Focus on peer-reviewed research, government data, reputable news
- Note the credibility and bias of sources

Use brave_web_search to find information, then write_to_database to record findings."""

    def build_messages(self, post_data: dict, context: dict = None):
        triage_result = context.get('triage_result', {})
        claims = triage_result.get('claims', [])
        
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user",
                "content": f"""
Research these claims from a Reddit post:

Original Post: {post_data['title']}
Claims to Research: {claims}

For each claim:
1. Search for credible sources
2. Evaluate the evidence 
3. Note contradicting information
4. Assess source credibility

Provide a comprehensive research report.
"""
            }
        ]
```

### 3. Response Agent
**Purpose**: Generate fact-based response to original post
**Model**: llama3.1:70b (capable writing)
**Tools**: [database_write_tool]

```python
class ResponseAgent(BaseAgent):
    def get_system_prompt(self):
        return """You are a response generation agent that creates factual corrections.

Your job is to:
1. Review the original post and research findings
2. Generate a helpful, respectful response
3. Cite credible sources for any corrections
4. Maintain a neutral, educational tone

Response guidelines:
- Be respectful and non-confrontational
- Focus on facts, not attacking the person
- Provide sources for claims
- Acknowledge uncertainty when appropriate
- Keep responses concise but informative

Use write_to_database to save your response draft."""

    def build_messages(self, post_data: dict, context: dict = None):
        research_result = context.get('research_result', {})
        
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {
                "role": "user",
                "content": f"""
Generate a response to this Reddit post based on research findings:

Original Post: {post_data['title']}
Content: {post_data.get('body', '')}
Research Findings: {research_result.get('findings', '')}
Sources: {research_result.get('sources', [])}

Create a helpful, fact-based response that addresses any misinformation while remaining respectful.
"""
            }
        ]
```

### 4. Editorial Agent
**Purpose**: Polish and fact-check the response
**Model**: llama3.1:8b (fast editing)
**Tools**: [database_write_tool]

```python
class EditorialAgent(BaseAgent):
    def get_system_prompt(self):
        return """You are an editorial agent that polishes responses for publication.

Your job is to:
1. Review the draft response for accuracy
2. Improve clarity and readability  
3. Ensure appropriate tone and formatting
4. Verify sources are properly cited
5. Check for any remaining errors

Editorial standards:
- Clear, concise writing
- Proper grammar and formatting
- Respectful, educational tone
- Accurate source citations
- Reddit-appropriate formatting

Use write_to_database to save the final edited response."""
```

## Tool Implementation

### Brave Search Tool Implementation
```python
async def execute_brave_search(query: str, count: int = 10, **kwargs) -> dict:
    """Execute Brave Search API call"""
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": os.getenv("BRAVE_API_KEY")
    }
    
    params = {
        "q": query,
        "count": count,
        "search_lang": kwargs.get("search_lang", "en"),
        "country": kwargs.get("country", "US"),
        "safesearch": kwargs.get("safesearch", "moderate")
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params
        )
        
    if response.status_code != 200:
        return {"error": f"Search failed: {response.status_code}"}
        
    data = response.json()
    
    # Process and format search results
    results = []
    for result in data.get("web", {}).get("results", []):
        results.append({
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "description": result.get("description", ""),
            "published": result.get("published", "")
        })
    
    return {
        "query": query,
        "results": results,
        "total_results": len(results)
    }
```

### Database Write Tool Implementation  
```python
async def execute_database_write(post_id: int, stage: str, content: dict, next_stage: str = None) -> dict:
    """Write processing results to database"""
    conn = get_db_connection()
    
    try:
        with conn.cursor() as cur:
            # Insert result
            cur.execute("""
                INSERT INTO queue_results (post_id, stage, result)
                VALUES (%s, %s, %s)
            """, (post_id, stage, json.dumps(content)))
            
            # Update post status and advance to next stage
            if next_stage:
                cur.execute("""
                    UPDATE posts 
                    SET queue_stage = %s, 
                        queue_status = 'pending',
                        processed_at = NOW()
                    WHERE id = %s
                """, (next_stage, post_id))
            else:
                cur.execute("""
                    UPDATE posts 
                    SET queue_status = 'completed',
                        processed_at = NOW()
                    WHERE id = %s
                """, (post_id,))
            
            conn.commit()
            
        return {"success": True, "message": f"Saved {stage} result for post {post_id}"}
        
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()
```

## Agent Configuration

### Endpoint Mapping
```python
AGENT_CONFIG = {
    "triage": {
        "class": TriageAgent,
        "model": "llama3.1:8b",
        "endpoint": "http://localhost:8001",
        "timeout": 30,
        "max_concurrent": 4
    },
    "research": {
        "class": ResearchAgent, 
        "model": "llama3.1:70b",
        "endpoint": "http://localhost:8002",
        "timeout": 300,
        "max_concurrent": 2
    },
    "response": {
        "class": ResponseAgent,
        "model": "llama3.1:70b", 
        "endpoint": "http://localhost:8002",
        "timeout": 180,
        "max_concurrent": 2
    },
    "editorial": {
        "class": EditorialAgent,
        "model": "llama3.1:8b",
        "endpoint": "http://localhost:8001", 
        "timeout": 60,
        "max_concurrent": 3
    }
}
```

This design provides a robust, tool-enabled agent system that can:
- Identify factual claims in Reddit posts
- Research claims using web search
- Generate fact-based responses
- Polish responses for publication
- Track all work in the database queue system