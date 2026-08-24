"""
AI Agent metrics — Prometheus counters and histograms for agent operations.

Tracks:
- Tasks submitted, completed, failed, approved, rejected
- Agent count by type and status
- LLM token usage
- Task execution duration
"""

try:
    from prometheus_client import Counter, Histogram, Gauge

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

    class Counter:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def inc(self, amount=1): pass

    class Histogram:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def observe(self, amount): pass

    class Gauge:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def set(self, value): pass
        def inc(self, amount=1): pass
        def dec(self, amount=1): pass


# ═══════════════════════════════════════════════════════════════════
# Task metrics
# ═══════════════════════════════════════════════════════════════════

ai_tasks_submitted_total = Counter(
    "ai_tasks_submitted_total",
    "Total AI agent tasks submitted",
    ["agent_type", "task_type"],
)

ai_tasks_completed_total = Counter(
    "ai_tasks_completed_total",
    "Total AI agent tasks completed successfully",
    ["agent_type", "task_type"],
)

ai_tasks_failed_total = Counter(
    "ai_tasks_failed_total",
    "Total AI agent tasks that failed",
    ["agent_type", "task_type"],
)

ai_tasks_approved_total = Counter(
    "ai_tasks_approved_total",
    "Total AI agent tasks approved by humans",
    ["agent_type", "task_type"],
)

ai_tasks_rejected_total = Counter(
    "ai_tasks_rejected_total",
    "Total AI agent tasks rejected by humans",
    ["agent_type", "task_type"],
)

ai_tasks_pending_approval = Gauge(
    "ai_tasks_pending_approval",
    "Number of tasks currently awaiting human approval",
    ["agent_type"],
)

# ═══════════════════════════════════════════════════════════════════
# Agent metrics
# ═══════════════════════════════════════════════════════════════════

ai_agents_total = Gauge(
    "ai_agents_total",
    "Total AI agents by type and status",
    ["agent_type", "status"],
)

# ═══════════════════════════════════════════════════════════════════
# LLM metrics
# ═══════════════════════════════════════════════════════════════════

ai_llm_tokens_used_total = Counter(
    "ai_llm_tokens_used_total",
    "Total LLM tokens consumed by AI agents",
    ["provider", "model"],
)

ai_task_duration_seconds = Histogram(
    "ai_task_duration_seconds",
    "AI task execution duration in seconds",
    ["agent_type", "task_type"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)


# ═══════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════

def record_task_submitted(agent_type: str, task_type: str) -> None:
    ai_tasks_submitted_total.labels(agent_type=agent_type, task_type=task_type).inc()

def record_task_completed(agent_type: str, task_type: str) -> None:
    ai_tasks_completed_total.labels(agent_type=agent_type, task_type=task_type).inc()

def record_task_failed(agent_type: str, task_type: str) -> None:
    ai_tasks_failed_total.labels(agent_type=agent_type, task_type=task_type).inc()

def record_task_approved(agent_type: str, task_type: str) -> None:
    ai_tasks_approved_total.labels(agent_type=agent_type, task_type=task_type).inc()

def record_task_rejected(agent_type: str, task_type: str) -> None:
    ai_tasks_rejected_total.labels(agent_type=agent_type, task_type=task_type).inc()

def record_llm_tokens(provider: str, model: str, tokens: int) -> None:
    ai_llm_tokens_used_total.labels(provider=provider, model=model).inc(amount=tokens)

def record_task_duration(agent_type: str, task_type: str, duration_seconds: float) -> None:
    ai_task_duration_seconds.labels(agent_type=agent_type, task_type=task_type).observe(duration_seconds)

def set_pending_approval_count(agent_type: str, count: int) -> None:
    ai_tasks_pending_approval.labels(agent_type=agent_type).set(count)

def set_agent_count(agent_type: str, status: str, count: int) -> None:
    ai_agents_total.labels(agent_type=agent_type, status=status).set(count)
