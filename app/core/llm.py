from dataclasses import dataclass, field

from openai import OpenAI

from app.config import settings


@dataclass
class ModelUsage:
    """Usage attributable to a single model."""

    calls: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "cached_tokens": self.cached_tokens,
            "completion_tokens": self.completion_tokens,
        }


@dataclass
class TokenUsage:
    """Accumulated token usage across calls (SiliconFlow reports cached tokens)."""

    calls: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    per_model: dict[str, ModelUsage] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def breakdown(self) -> dict[str, dict[str, int]]:
        return {model: usage.as_dict() for model, usage in self.per_model.items()}


class SiliconFlowLLM:
    def __init__(self):
        self.SILICON_FLOW_API_KEY = settings.silicon_flow_api_key.get_secret_value()
        self.SILICON_FLOW_BASE_URL = str(settings.silicon_flow_base_url)

        # models
        self.SILICON_FLOW_REASONING_MODEL = settings.reasoning_model
        self.SILICON_FLOW_NL2SQL_MODEL = settings.nl2sql_model
        self.SILICON_FLOW_HELPER_MODEL = settings.helper_model
        print("-" * 50)
        print(
            f"""\ncoder llm: {self.SILICON_FLOW_NL2SQL_MODEL}\nreasoning llm: {self.SILICON_FLOW_REASONING_MODEL}\nhelper llm: {self.SILICON_FLOW_HELPER_MODEL}\n"""
        )
        print("-" * 50)

        # client
        self.client = OpenAI(api_key=self.SILICON_FLOW_API_KEY, base_url=self.SILICON_FLOW_BASE_URL)

        # token accounting (consumed by the eval harness)
        self._usage = TokenUsage()

    # ------------------------------------------------------------- accounting

    def reset_usage(self) -> None:
        """Start a fresh accounting window (e.g. before one eval case)."""
        self._usage = TokenUsage()

    def usage(self) -> TokenUsage:
        """Usage accumulated since the last :meth:`reset_usage`."""
        return self._usage

    def _record(self, model: str, response) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        details = getattr(usage, "prompt_tokens_details", None)
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        cached = getattr(details, "cached_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0

        self._usage.calls += 1
        self._usage.prompt_tokens += prompt
        self._usage.cached_tokens += cached
        self._usage.completion_tokens += completion

        slot = self._usage.per_model.setdefault(model, ModelUsage())
        slot.calls += 1
        slot.prompt_tokens += prompt
        slot.cached_tokens += cached
        slot.completion_tokens += completion

    # ------------------------------------------------------------------ calls

    def call_coder(self, query, prompt):
        response = self.client.chat.completions.create(
            model=self.SILICON_FLOW_NL2SQL_MODEL,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": query}],
            temperature=0.7,
            max_tokens=4096,
        )
        self._record(self.SILICON_FLOW_NL2SQL_MODEL, response)
        return response.choices[0].message.content

    def call_llm(self, query, prompt):
        response = self.client.chat.completions.create(
            model=self.SILICON_FLOW_REASONING_MODEL,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": query}],
            temperature=0.7,
            max_tokens=4096,
        )
        self._record(self.SILICON_FLOW_REASONING_MODEL, response)
        return response.choices[0].message.content

    def call_helper(self, query, prompt):
        response = self.client.chat.completions.create(
            model=self.SILICON_FLOW_HELPER_MODEL,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": query}],
            temperature=0.7,
            max_tokens=4096,
        )
        self._record(self.SILICON_FLOW_HELPER_MODEL, response)
        return response.choices[0].message.content
