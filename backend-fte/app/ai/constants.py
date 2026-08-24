"""AI Agent constants — enums for agent types, statuses, task lifecycle, and workflows."""

import enum


class AgentType(str, enum.Enum):
    """Types of AI agents supported by the platform."""
    INVENTORY = "inventory"
    SOCIAL = "social"
    SALES = "sales"
    ANALYTICS = "analytics"
    CUSTOM = "custom"


class AgentStatus(str, enum.Enum):
    """Lifecycle states for an AI agent."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class TaskStatus(str, enum.Enum):
    """Lifecycle states for an agent task."""
    PENDING = "pending"
    PENDING_APPROVAL = "pending_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TaskType(str, enum.Enum):
    """Types of tasks agents can perform."""
    INVENTORY_CHECK = "inventory_check"
    INVENTORY_ADJUST = "inventory_adjust"
    STOCK_RECOMMENDATION = "stock_recommendation"
    CONTENT_GENERATE = "content_generate"
    POST_SCHEDULE = "post_schedule"
    SALES_ANALYSIS = "sales_analysis"
    PRICE_OPTIMIZATION = "price_optimization"
    WORKFLOW = "workflow"
    CUSTOM = "custom"


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW CONSTANTS
# ═══════════════════════════════════════════════════════════════════

MAX_WORKFLOW_STEPS: int = 20
MAX_WORKFLOW_INPUT_SIZE_BYTES: int = 10240  # 10KB
WORKFLOW_CONDITION_OPERATORS: list[str] = ["eq", "ne", "gt", "gte", "lt", "lte"]

# Default settings
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_TASK_TIMEOUT_SECONDS: int = 300
MAX_CONCURRENT_TASKS_PER_AGENT: int = 5
AGENT_NAME_MAX_LENGTH: int = 100
AGENT_DESCRIPTION_MAX_LENGTH: int = 500
