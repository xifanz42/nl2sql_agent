"""Model pricing for cost estimation (CNY per million tokens).

Prices are external and change over time; they are recorded here explicitly so a
cost figure always traces to a dated price list. Update from the provider's
pricing page when it changes.

Note: a model without a published cached-input tier is billed at its input price
for cached tokens (conservative).
"""

from __future__ import annotations

from typing import Any

# CNY per 1M tokens. Source: SiliconFlow pricing list, 2026-09.
PRICES_CNY_PER_MILLION: dict[str, dict[str, float]] = {
    "Qwen/Qwen3-Coder-30B-A3B-Instruct": {
        "input": 0.700,
        "cached_input": 0.700,  # no published cached tier
        "output": 2.800,
    },
    "deepseek-ai/DeepSeek-V3": {
        "input": 2.000,
        "cached_input": 0.200,
        "output": 8.000,
    },
    "Qwen/Qwen2.5-7B-Instruct": {
        "input": 0.000,
        "cached_input": 0.000,
        "output": 0.000,
    },
}


def cost_cny(
    model: str,
    *,
    prompt_tokens: int,
    cached_tokens: int,
    completion_tokens: int,
) -> float | None:
    """Cost of one model's token usage, or ``None`` if the model is unpriced."""
    price = PRICES_CNY_PER_MILLION.get(model)
    if price is None:
        return None
    cached = min(max(cached_tokens, 0), max(prompt_tokens, 0))
    uncached = max(prompt_tokens, 0) - cached
    return (
        uncached * price["input"] + cached * price["cached_input"] + completion_tokens * price["output"]
    ) / 1_000_000


def usage_cost_cny(model_usage: dict[str, dict[str, Any]]) -> tuple[float, list[str]]:
    """Total cost over a per-model usage breakdown.

    Returns ``(cost_cny, unpriced_models)``; a non-empty second element means the
    total is a lower bound.
    """
    total = 0.0
    unpriced: list[str] = []
    for model, usage in model_usage.items():
        amount = cost_cny(
            model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            cached_tokens=int(usage.get("cached_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )
        if amount is None:
            unpriced.append(model)
            continue
        total += amount
    return total, unpriced
