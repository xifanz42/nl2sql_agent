#!/usr/bin/env python3
"""Probe the configured LLM endpoint without touching the database.

    python scripts/check_llm.py                 # auth + model presence (no tokens)
    python scripts/check_llm.py --chat          # also send one tiny completion per tier
    python scripts/check_llm.py --provider deepseek

Why: provider failures (401 bad key, 402 empty balance, 404 model gone) surface
deep inside the eval as an opaque error. This script isolates the endpoint: it
prints which configured model ids the API actually serves, then optionally
proves a completion works. Exit code is non-zero when anything is wrong, so a
shell `&&` or CI step can gate on it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openai import APIStatusError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.config import settings  # noqa: E402
from app.core.llm import build_provider  # noqa: E402

# Hints for the status codes we actually hit in this project.
_STATUS_HINTS = {
    401: "API key rejected -- check the key in .env.",
    402: "Account balance is zero. Top up or apply a valid voucher in the "
    "SiliconFlow console; model choice cannot fix this.",
    403: "The key lacks access to this model (or the model is gated).",
    404: "Model id not served by this endpoint -- re-check the exact id.",
    429: "Rate limited; retry later.",
}


def _describe_error(exc: APIStatusError) -> str:
    status = exc.status_code
    body = getattr(exc, "body", None)
    return f"HTTP {status}: {_STATUS_HINTS.get(status, 'see response body')} body={body}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default="siliconflow",
        choices=["siliconflow", "deepseek"],
        help="which provider to probe (default: siliconflow)",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="send a tiny completion per tier (costs a few tokens)",
    )
    args = parser.parse_args()

    try:
        provider = build_provider(args.provider)
    except SystemExit as exc:  # missing credentials
        print(f"config error: {exc}")
        return 1

    print(f"provider : {provider.label}")
    print(f"base_url : {provider.client.base_url}")
    tiers = {
        "coder": provider.coder_model,
        "reasoning": provider.reasoning_model,
        "helper": provider.helper_model,
    }
    for tier, model in tiers.items():
        print(f"{tier:9}: {model}")

    ok = True

    # 1) Auth + catalogue. This call is free and proves key/network reachability.
    try:
        served = {m.id for m in provider.client.models.list().data}
        print(f"\n/models  : OK ({len(served)} models served)")
    except APIStatusError as exc:
        print(f"\n/models  : FAIL -- {_describe_error(exc)}")
        return 1
    except Exception as exc:  # noqa: BLE001 - report network/DNS/TLS failures verbatim
        print(f"\n/models  : FAIL -- {type(exc).__name__}: {exc}")
        return 1

    # 2) Each configured id must be present, or every call will 404 later.
    for tier, model in tiers.items():
        if model in served:
            print(f"  {tier:9} present: {model}")
        else:
            print(f"  {tier:9} MISSING: {model}")
            ok = False

    if not args.chat:
        print("\n(--chat skipped; add it to verify inference actually bills/runs)")
        return 0 if ok else 1

    # 3) One real completion per tier. This is where 402 balance errors appear.
    for tier, model in tiers.items():
        try:
            response = provider.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                temperature=0,
                max_tokens=8,
                extra_body=provider.extra_body,
            )
            text = (response.choices[0].message.content or "").strip()
            print(f"  {tier:9} chat OK -> {text!r}")
        except APIStatusError as exc:
            print(f"  {tier:9} chat FAIL -- {_describe_error(exc)}")
            ok = False
        except Exception as exc:  # noqa: BLE001
            print(f"  {tier:9} chat FAIL -- {type(exc).__name__}: {exc}")
            ok = False

    if not ok and args.provider == "siliconflow" and settings.silicon_flow_api_key:
        print(
            "\nNote: SiliconFlow's /models endpoint accepting a key does not mean "
            "the account can run inference -- 402 is billing, not configuration."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
