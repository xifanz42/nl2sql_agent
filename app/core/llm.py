from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from app.config import settings

# Decoding pinned for the eval: every system under test must decode alike, or a
# score difference can come from sampling rather than from the thing under test.
# Both call sites (``call_coder`` and the eval baselines) read these, so they
# cannot drift apart. Note a provider may ignore them -- DeepSeek's thinking
# mode drops ``temperature`` silently, which is why it has to be disabled.
EVAL_TEMPERATURE = 0.0
EVAL_MAX_TOKENS = 4096


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


@dataclass(frozen=True)
class Provider:
    """An OpenAI-compatible endpoint plus the model ids to call on it.

    Exists so the eval can pin the coder to a chosen vendor without editing
    ``.env``: the difference under test is *architecture*, and holding the model
    fixed -- then varying it deliberately -- is what makes that comparison mean
    anything.
    """

    label: str
    client: OpenAI
    coder_model: str
    helper_model: str
    reasoning_model: str
    extra_body: dict[str, Any] | None = None


def build_provider(
    name: str = "siliconflow", model: str | None = None, *, thinking: bool = False
) -> Provider:
    """Resolve a provider name into a client plus the model ids to use.

    ``thinking=False`` disables DeepSeek's reasoning mode. It is the default
    because that mode **ignores ``temperature``** (the API accepts the parameter
    and silently drops it) *and* injects extra instructions into the prompt, so a
    thinking run is not decoding-comparable with the others.
    """
    if name == "deepseek":
        if settings.ds_api_key is None:
            raise SystemExit("provider 'deepseek' needs DS_API_KEY in .env")
        coder = model or settings.ds_model_name
        # DeepSeek's endpoint only serves its own models, so every tier points there.
        return Provider(
            label=f"deepseek:{coder}",
            client=OpenAI(
                api_key=settings.ds_api_key.get_secret_value(),
                base_url=str(settings.ds_base_url),
            ),
            coder_model=coder,
            helper_model=coder,
            reasoning_model=coder,
            extra_body=None if thinking else {"thinking": {"type": "disabled"}},
        )
    if name != "siliconflow":
        raise SystemExit(f"unknown provider: {name}")
    return Provider(
        label="siliconflow",
        client=OpenAI(
            api_key=settings.silicon_flow_api_key.get_secret_value(),
            base_url=str(settings.silicon_flow_base_url),
        ),
        coder_model=model or settings.nl2sql_model,
        helper_model=settings.helper_model,
        reasoning_model=settings.reasoning_model,
    )


class SiliconFlowLLM:
    def __init__(self, provider: Provider | None = None):
        provider = provider or build_provider()
        self.provider = provider

        # models
        self.SILICON_FLOW_REASONING_MODEL = provider.reasoning_model
        self.SILICON_FLOW_NL2SQL_MODEL = provider.coder_model
        self.SILICON_FLOW_HELPER_MODEL = provider.helper_model
        print("-" * 50)
        print(
            f"""\ncoder llm: {self.SILICON_FLOW_NL2SQL_MODEL}\nreasoning llm: {self.SILICON_FLOW_REASONING_MODEL}\nhelper llm: {self.SILICON_FLOW_HELPER_MODEL}\n"""
        )
        print("-" * 50)

        # client
        self.client = provider.client

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
        kwargs: dict[str, Any] = {}
        if self.provider.extra_body is not None:
            kwargs["extra_body"] = self.provider.extra_body
        response = self.client.chat.completions.create(
            model=self.SILICON_FLOW_NL2SQL_MODEL,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": query}],
            temperature=EVAL_TEMPERATURE,
            max_tokens=EVAL_MAX_TOKENS,
            **kwargs,
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
