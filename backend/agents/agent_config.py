"""
Agent Configuration and Factory
Centralized configuration for all LLM agents
"""
import os
from typing import Dict, Any, Type, List
from .base_agent import BaseAgent, MockAgent
from .triage_agent import TriageAgent
from .research_agent import ResearchAgent
from .response_agent import ResponseAgent
from .editorial_agent import EditorialAgent


# Agent Configuration
AGENT_CONFIG = {
    "triage": {
        "class": TriageAgent,
        "model": "deepseek-r1:1.5b",
        "endpoint": os.getenv("TRIAGE_ENDPOINT", "http://192.168.1.71:11434"),
        "timeout": 120,  # 2 minutes for model loading + processing
        "max_concurrent": 4,
        "description": "Identifies posts with factual claims worth fact-checking",
        "cost_per_token": 0.0001
    },
    "research": {
        "class": ResearchAgent, 
        "model": "gpt-oss:20b",
        "endpoint": os.getenv("RESEARCH_ENDPOINT", "http://localhost:11434"),
        "timeout": 600,  # 10 minutes for model loading + web research + tool calls
        "max_concurrent": 2,
        "description": "Researches factual claims using web search",
        "cost_per_token": 0.001
    },
    "response": {
        "class": ResponseAgent,
        "model": "gpt-oss:20b", 
        "endpoint": os.getenv("RESPONSE_ENDPOINT", "http://localhost:11434"),
        "timeout": 300,  # 5 minutes for model loading + response generation
        "max_concurrent": 2,
        "description": "Generates fact-based responses to Reddit posts",
        "cost_per_token": 0.001
    },
    "editorial": {
        "class": EditorialAgent,
        "model": "gpt-oss:20b",
        "endpoint": os.getenv("EDITORIAL_ENDPOINT", "http://localhost:11434"), 
        "timeout": 180,  # 3 minutes for model loading + editing
        "max_concurrent": 3,
        "description": "Polishes and fact-checks response drafts",
        "cost_per_token": 0.0001
    }
}

# Stage transition rules
STAGE_TRANSITIONS = {
    "triage": {
        "success": "research",
        "reject": "rejected",
        "error": "triage"  # retry
    },
    "research": {
        "success": "response", 
        "unverifiable": "rejected",
        "error": "research"  # retry
    },
    "response": {
        "success": "editorial",
        "error": "response"  # retry
    },
    "editorial": {
        "success": "post_queue",
        "error": "editorial"  # retry
    }
}

# Environment-specific overrides
if os.getenv("USE_MOCK_AGENTS", "false").lower() == "true":
    print("Using mock agents for testing")
    for stage in AGENT_CONFIG:
        AGENT_CONFIG[stage]["class"] = MockAgent
        AGENT_CONFIG[stage]["endpoint"] = "http://mock"


class AgentFactory:
    """Factory for creating and managing agent instances"""

    @staticmethod
    def load_config_from_database(stage: str) -> dict:
        """Load agent configuration from database, falling back to defaults"""
        try:
            import psycopg

            connection_params = {
                "host": os.getenv("DB_HOST", "localhost"),
                "port": int(os.getenv("DB_PORT", "5432")),
                "dbname": os.getenv("DB_NAME", "redditmon"),
                "user": os.getenv("DB_USER", "redditmon"),
                "password": os.getenv("DB_PASSWORD", "supersecret")
            }

            with psycopg.connect(**connection_params) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT model, endpoint, timeout, max_concurrent, endpoint_type, api_key_env
                        FROM agent_config
                        WHERE agent_stage = %s
                    """, (stage,))

                    result = cur.fetchone()
                    if result:
                        print(f"📊 Loaded {stage} config from database: model={result[0]}, endpoint={result[1]}, type={result[4]}")
                        return {
                            "model": result[0],
                            "endpoint": result[1],
                            "timeout": result[2],
                            "max_concurrent": result[3],
                            "endpoint_type": result[4],
                            "api_key_env": result[5]
                        }
        except Exception as e:
            print(f"⚠️  Failed to load {stage} config from database: {e}")

        # Fall back to default configuration
        print(f"📋 Using default config for {stage}")
        return None

    @staticmethod
    def create_agent(stage: str) -> BaseAgent:
        """Create an agent instance for the given stage"""
        if stage not in AGENT_CONFIG:
            raise ValueError(f"Unknown agent stage: {stage}. Available: {list(AGENT_CONFIG.keys())}")

        # Try to load configuration from database first
        db_config = AgentFactory.load_config_from_database(stage)

        # Use database config if available, otherwise fall back to defaults
        if db_config:
            config = AGENT_CONFIG[stage].copy()  # Start with defaults
            config.update(db_config)  # Override with database values
        else:
            config = AGENT_CONFIG[stage]

        agent_class = config["class"]

        if agent_class == MockAgent:
            return MockAgent(stage)

        return agent_class(
            model=config["model"],
            endpoint=config["endpoint"],
            timeout=config["timeout"],
            endpoint_type=config.get("endpoint_type", "custom"),
            api_key_env=config.get("api_key_env")
        )
    
    @staticmethod
    def get_agent_config(stage: str) -> Dict[str, Any]:
        """Get configuration for a specific agent stage"""
        if stage not in AGENT_CONFIG:
            raise ValueError(f"Unknown agent stage: {stage}")
        return AGENT_CONFIG[stage].copy()
    
    @staticmethod
    def get_all_stages() -> List[str]:
        """Get list of all available agent stages"""
        return list(AGENT_CONFIG.keys())
    
    @staticmethod
    def get_next_stage(current_stage: str, result_status: str = "success") -> str:
        """Determine next stage based on current stage and result status"""
        transitions = STAGE_TRANSITIONS.get(current_stage, {})
        return transitions.get(result_status, "completed")
    
    @staticmethod
    def validate_environment() -> Dict[str, Any]:
        """Validate that required environment variables are set"""
        validation_results = {
            "valid": True,
            "missing": [],
            "warnings": []
        }
        
        # Check required environment variables
        required_vars = ["BRAVE_API_KEY"]
        for var in required_vars:
            if not os.getenv(var):
                validation_results["missing"].append(var)
                validation_results["valid"] = False
        
        # Check optional endpoint configurations
        optional_vars = [
            "TRIAGE_ENDPOINT", 
            "RESEARCH_ENDPOINT", 
            "RESPONSE_ENDPOINT", 
            "EDITORIAL_ENDPOINT"
        ]
        for var in optional_vars:
            if not os.getenv(var):
                validation_results["warnings"].append(f"{var} not set, using default")
        
        return validation_results


# Agent performance tracking
class AgentMetrics:
    """Track performance metrics for agents"""
    
    def __init__(self):
        self.metrics = {
            stage: {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_processing_time": 0.0,
                "average_processing_time": 0.0,
                "total_cost": 0.0
            }
            for stage in AGENT_CONFIG.keys()
        }
    
    def record_request(self, stage: str, success: bool, processing_time: float, token_count: int = 0):
        """Record a completed agent request"""
        if stage not in self.metrics:
            return
        
        stage_metrics = self.metrics[stage]
        stage_metrics["total_requests"] += 1
        
        if success:
            stage_metrics["successful_requests"] += 1
        else:
            stage_metrics["failed_requests"] += 1
        
        stage_metrics["total_processing_time"] += processing_time
        stage_metrics["average_processing_time"] = (
            stage_metrics["total_processing_time"] / stage_metrics["total_requests"]
        )
        
        # Calculate cost
        cost_per_token = AGENT_CONFIG[stage]["cost_per_token"]
        stage_metrics["total_cost"] += token_count * cost_per_token
    
    def get_metrics(self, stage: str = None) -> Dict[str, Any]:
        """Get metrics for a specific stage or all stages"""
        if stage:
            return self.metrics.get(stage, {})
        return self.metrics.copy()
    
    def reset_metrics(self, stage: str = None):
        """Reset metrics for a specific stage or all stages"""
        if stage:
            if stage in self.metrics:
                self.metrics[stage] = {
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "total_processing_time": 0.0,
                    "average_processing_time": 0.0,
                    "total_cost": 0.0
                }
        else:
            for stage_key in self.metrics:
                self.reset_metrics(stage_key)


# Global metrics instance
agent_metrics = AgentMetrics()


# Utility functions
def get_agent_summary() -> Dict[str, Any]:
    """Get summary of all configured agents"""
    summary = {
        "total_agents": len(AGENT_CONFIG),
        "stages": list(AGENT_CONFIG.keys()),
        "endpoints": {},
        "models": {},
        "estimated_monthly_cost": 0
    }
    
    for stage, config in AGENT_CONFIG.items():
        endpoint = config["endpoint"]
        model = config["model"]
        
        if endpoint not in summary["endpoints"]:
            summary["endpoints"][endpoint] = []
        summary["endpoints"][endpoint].append(stage)
        
        if model not in summary["models"]:
            summary["models"][model] = []
        summary["models"][model].append(stage)
    
    return summary


def health_check_agents() -> Dict[str, Any]:
    """Perform health check on all agent endpoints"""
    # This would implement actual health checks to agent endpoints
    # For now, return a placeholder
    return {
        "status": "healthy",
        "agents": {stage: "online" for stage in AGENT_CONFIG.keys()},
        "timestamp": "2024-01-01T00:00:00Z"
    }


# Example usage
if __name__ == "__main__":
    import json
    
    # Validate environment
    validation = AgentFactory.validate_environment()
    print("Environment validation:", json.dumps(validation, indent=2))
    
    # Get agent summary
    summary = get_agent_summary()
    print("\nAgent summary:", json.dumps(summary, indent=2))
    
    # Test agent creation
    try:
        triage_agent = AgentFactory.create_agent("triage")
        print(f"\nCreated triage agent: {triage_agent.__class__.__name__}")
        print(f"Agent info: {json.dumps(triage_agent.get_agent_info(), indent=2)}")
    except Exception as e:
        print(f"Error creating agent: {e}")