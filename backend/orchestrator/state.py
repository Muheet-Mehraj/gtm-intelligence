from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class AgentState:
    """
    Central state object shared across all agents.
    Holds data, decisions, and execution metadata.
    """

    # input
    query: str

    # planning
    plan: Optional[Dict[str, Any]] = None

    # data flow
    raw_results: List[Dict[str, Any]] = field(default_factory=list)
    enriched_results: List[Dict[str, Any]] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)

    # output
    gtm_strategy: Optional[Dict[str, Any]] = None

    # critic
    critic_status: Optional[str] = None
    critic_feedback: Optional[str] = None

    # execution control
    retry_count: int = 0
    max_retries: int = 3

    # quality
    confidence: float = 0.0

    # memory — used by WebSocket path for critic feedback loop
    memory: Dict[str, Any] = field(default_factory=dict)

    # observability
    reasoning_trace: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def add_trace(self, message: str) -> None:
        self.reasoning_trace.append(message)

    def add_log(self, message: str) -> None:
        self.logs.append(message)

    def set_critic(self, status: str, feedback: str) -> None:
        self.critic_status = status
        self.critic_feedback = feedback

    def increment_retry(self) -> None:
        self.retry_count += 1

    def should_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def reset_for_retry(self) -> None:
        self.raw_results.clear()
        self.enriched_results.clear()
        self.signals.clear()
        self.gtm_strategy = None
        self.critic_status = None
        self.critic_feedback = None