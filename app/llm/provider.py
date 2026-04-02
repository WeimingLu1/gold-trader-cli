"""LLM provider abstraction — supports OpenAI, Anthropic, and mock."""
from abc import ABC, abstractmethod
from app.llm.schemas import LLMResponse
from app.config import get_settings


class LLMProvider(ABC):
    """Abstract interface for all LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Send a prompt and return a structured LLM response."""
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Mock provider for development and testing — returns predictable structured output."""

    MODEL_NAME = "mock"

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Return a deterministic mock response for testing."""
        # Simulate the structure the real provider would return
        return LLMResponse(
            raw_text="mock_analyst_output",
            parsed={
                "direction": "neutral",
                "confidence": 0.5,
                "primary_drivers": ["Mock: No real data available."],
                "counter_drivers": ["Mock: Placeholder response."],
                "narrative": "This is a mock analyst narrative generated for dev/test purposes.",
                "key_events": [],
            },
            model_used=self.MODEL_NAME,
        )


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible provider (GPT-4o, GPT-4o-mini, etc.)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        import os
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = get_settings().llm_model

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """
        Call OpenAI Chat Completions API.

        Raises:
            ImportError if openai SDK not installed.
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

        settings = get_settings()
        client = AsyncOpenAI(api_key=self.api_key or None, base_url=self.base_url or None)

        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            **kwargs,
        )

        raw = response.choices[0].message.content or ""
        parsed = self._parse_structured_output(raw)

        return LLMResponse(
            raw_text=raw,
            parsed=parsed,
            model_used=f"{self.model}",
            tokens_used=response.usage.total_tokens if response.usage else None,
        )

    def _parse_structured_output(self, raw: str) -> dict:
        """
        Parse structured JSON from LLM response.

        Attempts JSON extraction from markdown code blocks first,
        then falls back to returning the raw text with a warning.
        """
        import json, re

        # Try to extract JSON from markdown code block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Try raw JSON
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        return {"raw": raw}


def build_provider() -> LLMProvider:
    """Factory function to build the configured LLM provider."""
    settings = get_settings()

    if settings.llm_api_key == "mock" or settings.llm_model == "mock":
        return MockLLMProvider()

    if settings.llm_api_key:
        return OpenAIProvider(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )

    # No API key provided — fall back to mock
    return MockLLMProvider()
