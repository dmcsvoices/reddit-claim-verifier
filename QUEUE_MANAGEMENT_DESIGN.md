# Queue Management System Design

## Overview

The Queue Management System orchestrates LLM endpoints and manages the flow of Reddit posts through processing stages. Each stage has a dedicated LLM endpoint with input/output queue management, while agents write results directly to the database using tools.

## Architecture Components

### System Flow
```
Database Queue Tables → Queue Manager → LLM Endpoints → Database Updates
                            ↑                ↓
                       Status Tracking ← Tool Responses
```

### Core Components

#### 1. LLM Endpoint Management

**Single Persistent Agent Instances**
- One persistent agent instance per processing stage
- Reused across multiple requests to reduce initialization overhead
- Maintains connection pooling to Ollama endpoints

```python
endpoints = {
    "triage": TriageAgent(model="llama3.1:8b", endpoint="http://localhost:8001"),
    "research": ResearchAgent(model="llama3.1:70b", endpoint="http://localhost:8002"),
    "response": ResponseAgent(model="llama3.1:70b", endpoint="http://localhost:8002"), 
    "editorial": EditorialAgent(model="llama3.1:8b", endpoint="http://localhost:8001")
}
```

**Endpoint Status Tracking**
```python
endpoint_status = {
    "triage": {"available": True, "current_load": 0, "max_concurrent": 4},
    "research": {"available": True, "current_load": 0, "max_concurrent": 2},
    "response": {"available": True, "current_load": 0, "max_concurrent": 2},
    "editorial": {"available": True, "current_load": 0, "max_concurrent": 3}
}
```

#### 2. Queue Processing Flow

**Input Queue Logic**
Posts are pulled from the database based on stage, status, and priority:

```sql
SELECT id, title, body, author, subreddit, url, metadata
FROM posts 
WHERE queue_stage = 'triage' 
  AND queue_status = 'pending'
  AND (assigned_to IS NULL OR assigned_at < NOW() - INTERVAL '5 minutes')
ORDER BY COALESCE(metadata->>'priority', '5')::int DESC, created_utc ASC
LIMIT max_concurrent;
```

**Processing Steps**
1. **Query Database** → Get pending posts for current stage
2. **Assign to Worker** → Mark post as 'processing', set assigned_to/assigned_at
3. **Call LLM Agent** → Process with appropriate agent + context from previous stages
4. **Agent Uses Tools** → Agents write results via database_write_tool
5. **Update Status** → Queue manager updates post status based on tool results

#### 3. Context Retrieval System

Agents need results from previous processing stages for context:

```python
async def get_processing_context(post_id: int, current_stage: str) -> dict:
    """Get all previous processing results for context"""
    previous_stages = {
        "research": ["triage"],
        "response": ["triage", "research"], 
        "editorial": ["triage", "research", "response"]
    }
    
    context = {}
    for stage in previous_stages.get(current_stage, []):
        result = await get_latest_result(post_id, stage)
        if result:
            context[f"{stage}_result"] = result
    
    return context
```

#### 4. Database Status Tracking

**Post Status Lifecycle**
```
pending → processing → completed → (next stage: pending)
pending → processing → rejected/failed → (retry or dead letter)
```

**Agent-Controlled Transitions**
- Agents decide next stage via `database_write_tool`
- Queue manager handles assignment/clearing only
- Agents have full context about processing decisions

**Status Update Logic**
```python
async def handle_agent_completion(post_id: int, stage: str, agent_result: dict):
    """Handle completion of agent processing"""
    
    if not agent_result.get("success"):
        # Handle failure - retry or mark as failed
        await update_post_status(post_id, "failed", retry_count + 1)
        return
    
    # Check if agent wrote to database via tools
    tool_calls = agent_result.get("tool_calls", [])
    database_writes = [tc for tc in tool_calls if tc["tool"] == "write_to_database"]
    
    if database_writes:
        # Agent handled status update via database_write_tool
        # Queue manager just needs to clear assignment
        await clear_assignment(post_id)
    else:
        # No database write - mark as completed but don't advance
        await update_post_status(post_id, "completed")
```

#### 5. Worker Assignment & Load Balancing

**Polling-Based Processing**
- Each stage polls database independently
- Configurable intervals based on processing complexity
- Simple, reliable, easy to monitor and debug

**Concurrency Control**
```python
class StageWorker:
    async def process_stage_queue(self, stage: str):
        while self.running:
            # Check endpoint availability
            if not self.can_process_more(stage):
                await asyncio.sleep(self.poll_intervals[stage])
                continue
            
            # Get pending posts
            posts = await self.get_pending_posts(stage, limit=available_slots)
            
            # Process posts concurrently
            tasks = []
            for post in posts:
                task = asyncio.create_task(self.process_post(post, stage))
                tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            await asyncio.sleep(self.poll_intervals[stage])
```

## Configuration

### Queue Processing Settings
```python
QUEUE_CONFIG = {
    "poll_intervals": {
        "triage": 5,      # seconds - fast processing
        "research": 15,   # longer due to web search complexity
        "response": 10,   # moderate complexity
        "editorial": 5    # fast editing/polishing
    },
    "assignment_timeout": 300,  # 5 minutes before reassignment
    "max_retries": 3,
    "retry_delays": [60, 300, 900],  # exponential backoff (1min, 5min, 15min)
    "dead_letter_threshold": 3  # failed attempts before dead letter queue
}
```

### Stage Concurrency Limits
```python
CONCURRENCY_LIMITS = {
    "triage": 4,     # Fast, cheap model - higher concurrency
    "research": 2,   # Slower, expensive model + web search
    "response": 2,   # Slower, expensive model for quality writing
    "editorial": 3   # Fast model for polishing
}
```

## Key Design Decisions

### 1. Database-Driven Queue State
- **No in-memory queues** - all state persisted in PostgreSQL
- **Crash-resistant** - system recovers automatically on restart
- **Observable** - full audit trail and status visibility
- **Natural priority** - SQL ORDER BY for priority handling
- **Built-in retry** - exponential backoff with database tracking

### 2. Single Persistent Agent Instances
- **Reduced overhead** - no repeated initialization costs
- **Connection reuse** - maintains HTTP connections to Ollama
- **Stateful optimization** - agents can cache configurations
- **Resource efficiency** - one process per stage type

### 3. Agent-Controlled Flow Decisions
- **Intelligent transitions** - agents decide next stage based on results
- **Context awareness** - agents see full processing history
- **Flexible routing** - can skip stages or branch based on content
- **Error recovery** - agents can retry or redirect on failures

### 4. Polling-Based Architecture
- **Simple debugging** - easy to trace processing flow
- **Configurable timing** - adjust poll rates per stage complexity  
- **Load balancing** - natural distribution across available workers
- **Fault tolerance** - isolated failures don't cascade

### 5. Load-Aware Processing
- **Respect limits** - honor max_concurrent per endpoint
- **Graceful degradation** - handle endpoint failures smoothly
- **Timeout recovery** - reassign stuck processing automatically
- **Priority handling** - process high-priority posts first

## Error Handling & Recovery

### Timeout Recovery
- Posts assigned longer than `assignment_timeout` are automatically reassigned
- Prevents stuck processing from blocking queues
- Graceful handling of crashed or slow endpoints

### Retry Logic
- Failed posts retry with exponential backoff
- Maximum retry attempts before dead letter queue
- Tracking of failure reasons for debugging

### Dead Letter Queue
- Posts that exceed max retries go to dead letter queue
- Manual inspection and reprocessing capability
- Prevents infinite retry loops

## Monitoring & Observability

### Queue Metrics
- Queue depth per stage
- Processing time histograms
- Success/failure rates
- Endpoint availability status

### Database Tracking
- Complete processing audit trail
- Stage transition history
- Error logs and retry counts
- Performance metrics per post type

## Benefits

- **Scalable**: Easy to add endpoints or adjust concurrency
- **Resilient**: Database persistence, timeout recovery, retry logic
- **Observable**: Full audit trail, clear status tracking  
- **Flexible**: Agents control their own flow decisions
- **Simple**: Polling easier to debug than complex event systems
- **Cost-aware**: Different models for different complexity levels
- **Maintainable**: Clear separation of concerns between components

## Implementation Phases

### Phase 1: Core Queue Manager
- Database connection management
- Basic polling and assignment logic
- Agent instantiation and lifecycle

### Phase 2: Worker System
- Stage-specific workers with concurrency control
- Context retrieval for multi-stage processing
- Status update and flow management

### Phase 3: Error Handling & Recovery
- Retry logic with exponential backoff
- Timeout detection and reassignment
- Dead letter queue management

### Phase 4: Monitoring & Optimization
- Performance metrics collection
- Queue depth monitoring
- Load balancing optimization