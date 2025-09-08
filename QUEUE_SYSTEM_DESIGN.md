# LLM Queue Processing System Design

## Overview

This document outlines the design for implementing a multi-stage LLM queue processing system on top of the existing Reddit monitoring application. The system will process Reddit posts through a pipeline of specialized LLM agents to identify claims, research them, generate responses, and post back to Reddit.

## System Architecture

### Queue Flow
```
Reddit Scan → Triage → Research → Response → Editorial → Post Queue → Reddit
```

### Database Schema

#### Enhanced Posts Table
```sql
ALTER TABLE posts ADD COLUMN 
    queue_stage VARCHAR(20) DEFAULT 'triage',
    queue_status VARCHAR(20) DEFAULT 'pending',
    assigned_to VARCHAR(50) NULL,
    assigned_at TIMESTAMPTZ NULL,
    processed_at TIMESTAMPTZ NULL,
    retry_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}';
```

#### Supporting Tables
```sql
-- Store results from each processing stage
CREATE TABLE queue_results (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES posts(id),
    stage VARCHAR(20) NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Track available LLM endpoints
CREATE TABLE llm_endpoints (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    url VARCHAR(200) NOT NULL,
    capabilities JSONB NOT NULL,
    max_concurrent INTEGER DEFAULT 1,
    current_load INTEGER DEFAULT 0
);
```

### Queue Stages

1. **Triage Queue** (`triage`)
   - Status: `pending`, `processing`, `completed`, `rejected`
   - Purpose: Identify posts that make factual claims
   - Output: Claim classification and extracted claims

2. **Research Queue** (`research`)
   - Status: `pending`, `processing`, `completed`, `failed`
   - Purpose: Research identified claims using web search
   - Output: Research findings and source citations

3. **Response Queue** (`response`) 
   - Status: `pending`, `processing`, `completed`, `failed`
   - Purpose: Generate response based on claim and research
   - Output: Draft response with supporting evidence

4. **Editorial Queue** (`editorial`)
   - Status: `pending`, `processing`, `completed`, `failed`
   - Purpose: Edit and fact-check the response
   - Output: Final polished response

5. **Post Queue** (`post_queue`)
   - Status: `pending`, `processing`, `completed`, `failed`, `rate_limited`
   - Purpose: Post responses back to Reddit with rate limiting
   - Output: Posted comment ID and metadata

## LLM Endpoint Integration

### Configuration Structure
```python
LLM_ENDPOINTS = {
    "triage": {
        "url": "http://localhost:8001/chat",  # Fast, cheap model
        "timeout": 30,
        "max_concurrent": 4,
        "model": "llama-3.1-8b",
        "cost_per_token": 0.0001
    },
    "research": {
        "url": "http://localhost:8002/chat",  # Capable model
        "timeout": 300,  # 5 min for web research
        "max_concurrent": 2,
        "model": "llama-3.1-70b",
        "cost_per_token": 0.001
    },
    "response": {
        "url": "http://localhost:8002/chat",
        "timeout": 180,
        "max_concurrent": 2,
        "model": "llama-3.1-70b",
        "cost_per_token": 0.001
    },
    "editorial": {
        "url": "http://localhost:8001/chat",
        "timeout": 60,
        "max_concurrent": 3,
        "model": "llama-3.1-8b",
        "cost_per_token": 0.0001
    }
}
```

### Load Balancing Strategy
- Track concurrent requests per endpoint
- Queue items when endpoints at capacity
- Prefer faster endpoints for time-sensitive stages
- Fallback to alternative endpoints when available

## Worker System Design

### Queue Processor Architecture
```python
class QueueProcessor:
    async def process_stage(self, stage: str):
        while True:
            # Get pending items for this stage
            items = await self.get_pending_items(stage)
            
            # Process each item if endpoint available
            for item in items:
                if await self.assign_to_endpoint(item, stage):
                    await self.process_item(item, stage)
            
            await asyncio.sleep(self.poll_interval[stage])

    async def process_item(self, item, stage):
        try:
            # Call appropriate LLM agent
            result = await self.call_llm_agent(item, stage)
            
            # Save result and advance to next stage
            await self.save_result_and_advance(item, result, stage)
            
        except Exception as e:
            await self.handle_processing_error(item, e)
```

### Background Task Integration
- Each stage runs as separate async background task
- Configurable polling intervals per stage
- Graceful shutdown handling with task cleanup
- Health check endpoints for monitoring

## Queue Management Features

### Retry Logic
- Exponential backoff for failed items
- Maximum retry limits per stage
- Dead letter queue for permanently failed items
- Manual retry capability through API

### Priority System
- Score posts based on upvotes, comments, age
- Process higher priority items first
- Configurable priority thresholds per stage

### Monitoring & Observability
- Queue depth metrics per stage
- Processing time histograms
- Error rate tracking
- LLM endpoint performance metrics

## Implementation Phases

### Phase 1: Database Schema & Queue Infrastructure
- [ ] Extend posts table with queue columns
- [ ] Create queue_results and llm_endpoints tables
- [ ] Add queue management API endpoints (`/queue/status`, `/queue/retry`)
- [ ] Basic queue viewer in frontend dashboard

### Phase 2: LLM Integration Layer
- [ ] Create LLM client abstraction with timeout/retry
- [ ] Implement endpoint load balancing and health checks
- [ ] Add mock LLM responses for testing
- [ ] Configuration management for endpoints

### Phase 3: Queue Processors
- [ ] Triage agent implementation (claim detection)
- [ ] Research agent implementation (web search + analysis)
- [ ] Response agent implementation (synthesis)
- [ ] Editorial agent implementation (polish/fact-check)

### Phase 4: Reddit Integration & Production
- [ ] Rate-limited Reddit posting with backoff
- [ ] Comment monitoring for engagement tracking
- [ ] Performance metrics collection and dashboards
- [ ] Production deployment configuration

## Key Benefits

- **Database-driven**: Persistent, crash-resistant queues
- **Scalable**: Easy to add more LLM endpoints or workers
- **Observable**: Full audit trail of processing pipeline
- **Configurable**: Timeouts, retries, concurrency per stage
- **Testable**: Mock endpoints for development and testing
- **Cost-aware**: Track and optimize LLM usage costs

## Development Considerations

### Local Development Setup
- Mock LLM endpoints for testing without actual models
- Reduced polling intervals for faster iteration
- SQLite option for simplified local database
- Docker Compose integration for full stack testing

### Production Considerations
- Connection pooling for database and HTTP clients
- Metrics export to monitoring systems
- Log aggregation for debugging
- Backup and recovery procedures for queue state