"""Single source of truth for every eval file location.

Keeping paths here means runner/reporter/execute never hardcode strings, and the
public/private split is visible in one place (enforced by .gitignore):

* dataset + expected-cache     -> private (they mirror the closed-source DB)
* ``reports/<model>/*.md``     -> public
* ``raw/<model>/*.raw.jsonl``  -> private (the whole directory is ignored)

Per-run artifacts are filed under a directory named after the model: with more
than one model in play, a bare ``direct-<stamp>.md`` no longer says which model
produced it. The ledger stays the index -- it records the report path relative
to ``output_dir``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app import PROJECT_ROOT


#: Directory for runs that make no model call at all (e.g. the oracle).
NO_MODEL_SLUG = "no-model"


def model_slug(model: str | None) -> str:
    """Directory name for a model id.

    ``Qwen/Qwen3-Coder-30B-A3B-Instruct`` -> ``qwen3-coder-30b-a3b-instruct``.
    Derived rather than looked up, so a new model needs no registration.
    """
    if not model:
        return NO_MODEL_SLUG
    return re.sub(r"[^a-z0-9]+", "-", model.split("/")[-1].lower()).strip("-")


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

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"

    @property
    def raw_dir(self) -> Path:
        return self.output_dir / "raw"

    def report(self, model: str, system: str, stamp: str) -> Path:
        """Public, sanitized markdown report."""
        return self.reports_dir / model_slug(model) / f"{system}-{stamp}.md"

    def raw(self, model: str, system: str, stamp: str) -> Path:
        """Private per-case dump (the containing directory is ignored)."""
        return self.raw_dir / model_slug(model) / f"{system}-{stamp}.raw.jsonl"

    def ledger_report(self, model: str, system: str, stamp: str) -> str:
        """Report path as the ledger records it: relative to ``output_dir``."""
        return str(self.report(model, system, stamp).relative_to(self.output_dir))

    def raw_for(self, ledger_report: str) -> Path:
        """The raw dump belonging to a ledger-recorded report path.

        The two live in sibling trees (``reports/`` and ``raw/``) with the same
        <model>/<system>-<stamp> shape, so a reader holding only the ledger can
        still find the private per-case dump.
        """
        under_model = Path(ledger_report).relative_to("reports")
        return self.raw_dir / under_model.with_suffix(".raw.jsonl")
