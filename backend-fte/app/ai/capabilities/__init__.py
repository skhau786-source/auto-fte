"""
AI Agent Capabilities — controlled tool layer for agent actions.

Agents do NOT directly manipulate database tables or external APIs.
Instead, they call capabilities which delegate to existing services.

Architecture:
  Agent → Capability → Existing Service → Database / External API

Each capability declares:
- name
- read/write type
- required permission
- approval requirement
- supported agent types
"""

__version__ = "1.0.0"
