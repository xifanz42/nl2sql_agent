"""Single source of truth for every eval file location.

Keeping paths here means runner/reporter/execute never hardcode strings, and the
public/private split is visible in one place (enforced by .gitignore):

* dataset + expected-cache  -> private (they mirror the closed-source DB)
* report (*.md)             -> public
* raw (*.raw.jsonl)         -> private
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app import PROJECT_ROOT


@dataclass(frozen=True)
class EvalPaths:
    dataset: Path
    expected_cache: Path
    output_dir: Path

    @classmethod
    def default(cls) -> "EvalPaths":
        return cls(
            dataset=PROJECT_ROOT / "tests" / "eval" / "golden_dataset.jsonl",
            expected_cache=PROJECT_ROOT / "tests" / "eval" / "expected_results.jsonl",
            output_dir=PROJECT_ROOT / "eval_results",
        )

    def report(self, stamp: str) -> Path:
        """Public, sanitized markdown report."""
        return self.output_dir / f"{stamp}.md"

    def raw(self, stamp: str) -> Path:
        """Private per-case dump (ignored via *.raw.jsonl)."""
        return self.output_dir / f"{stamp}.raw.jsonl"
