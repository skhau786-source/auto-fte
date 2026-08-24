"""
LLM Client Abstraction — provides a unified interface for LLM providers.

Supports OpenAI-compatible APIs (OpenAI, Azure OpenAI, local LLMs).
Also supports Anthropic via a separate code path.

All API keys come from environment variables and are NEVER stored in the database.

Usage:
    client = get_llm_client()
    response = await client.complete("Summarize this inventory report", model="gpt-4o-mini")
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""
    content: str = ""
    model: str = ""
    provider: str = ""
    tokens_used: int = 0
    finish_reason: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class LLMMessage:
    """A single message in a conversation."""
    role: str  # "system", "user", "assistant"
    content: str


class BaseLLMClient(ABC):
    """Abstract base class for all LLM clients."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""
        ...

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this client has valid credentials."""
        ...

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a single-turn completion request."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send a multi-turn chat completion request."""
        ...

    async def close(self) -> None:
        """Clean up resources."""
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI API client (also compatible with Azure OpenAI and local LLMs)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "gpt-4o-mini",
    ):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self._default_model = default_model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        """Lazy-init the OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                kwargs = {"api_key": self._api_key}
                if self._base_url:
                    kwargs["base_url"] = self._base_url
                self._client = AsyncOpenAI(**kwargs)
            except ImportError:
                raise ImportError(
                    "openai package not installed. Run: pip install openai"
                )
        return self._client

    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.chat(
            messages=[LLMMessage(role=m["role"], content=m["content"]) for m in messages],
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def chat(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        client = self._get_client()
        use_model = model or self._default_model

        try:
            response = await client.chat.completions.create(
                model=use_model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            choice = response.choices[0] if response.choices else None
            content = choice.message.content if choice and choice.message else ""
            tokens = response.usage.total_tokens if response.usage else 0

            return LLMResponse(
                content=content or "",
                model=use_model,
                provider=self.provider_name,
                tokens_used=tokens,
                finish_reason=choice.finish_reason if choice else "",
                raw=response.model_dump() if hasattr(response, "model_dump") else {},
            )
        except Exception as exc:
            logger.error("OpenAI API error: %s", exc)
            raise

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "claude-sonnet-4-20250514",
    ):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._default_model = default_model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=self._api_key)
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. Run: pip install anthropic"
                )
        return self._client

    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        client = self._get_client()
        use_model = model or self._default_model

        try:
            kwargs = {
                "model": use_model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = await client.messages.create(**kwargs)

            content = ""
            if response.content:
                content = response.content[0].text if response.content else ""

            tokens = (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0

            return LLMResponse(
                content=content,
                model=use_model,
                provider=self.provider_name,
                tokens_used=tokens,
                finish_reason=response.stop_reason or "",
                raw={},
            )
        except Exception as exc:
            logger.error("Anthropic API error: %s", exc)
            raise

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None


class MockLLMClient(BaseLLMClient):
    """
    Mock LLM client for testing.

    Returns configurable responses without making real API calls.
    """

    def __init__(self, response: str = "Mock LLM response", tokens: int = 50):
        self._response = response
        self._tokens = tokens

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def is_configured(self) -> bool:
        return True

    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        return LLMResponse(
            content=self._response,
            model=model or "mock-model",
            provider=self.provider_name,
            tokens_used=self._tokens,
            finish_reason="stop",
        )

    async def chat(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        return LLMResponse(
            content=self._response,
            model=model or "mock-model",
            provider=self.provider_name,
            tokens_used=self._tokens,
            finish_reason="stop",
        )


# ═══════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════

_client_instance: Optional[BaseLLMClient] = None


def get_llm_client() -> BaseLLMClient:
    """
    Get the configured LLM client.

    Selection priority:
    1. OPENAI_API_KEY → OpenAI client
    2. ANTHROPIC_API_KEY → Anthropic client
    3. Fallback → Mock client (logs warning)

    The client is a singleton — reuse across the application.
    """
    global _client_instance

    if _client_instance is not None:
        return _client_instance

    openai_key = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    if openai_key:
        _client_instance = OpenAIClient()
        logger.info("LLM client initialized: OpenAI (model=%s)", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    elif anthropic_key:
        _client_instance = AnthropicClient()
        logger.info("LLM client initialized: Anthropic (model=%s)", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))
    else:
        logger.warning(
            "No LLM API key configured. Agent tasks will use mock responses. "
            "Set OPENAI_API_KEY or ANTHROPIC_API_KEY to enable real AI capabilities."
        )
        _client_instance = MockLLMClient()

    return _client_instance


def reset_llm_client() -> None:
    """Reset the singleton (for testing)."""
    global _client_instance
    _client_instance = None


def set_llm_client(client: BaseLLMClient) -> None:
    """Override the singleton with a custom client (for testing)."""
    global _client_instance
    _client_instance = client
