"""LLM call wrappers normalize empty content instead of returning None."""

from types import SimpleNamespace

from app.core.llm import SiliconFlowLLM, TokenUsage


class FakeCompletions:
    def __init__(self, content):
        self.content = content

    def create(self, **kwargs):
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=None,
        )


def _engine(content):
    engine = SiliconFlowLLM.__new__(SiliconFlowLLM)
    engine.provider = SimpleNamespace(extra_body=None, label="test")
    engine.client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions(content))
    )
    engine.SILICON_FLOW_NL2SQL_MODEL = "coder"
    engine.SILICON_FLOW_REASONING_MODEL = "reasoner"
    engine.SILICON_FLOW_HELPER_MODEL = "helper"
    engine._usage = TokenUsage()
    return engine


def test_none_content_becomes_empty_string():
    engine = _engine(None)

    assert engine.call_coder("q", "p") == ""
    assert engine.call_llm("q", "p") == ""
    assert engine.call_helper("q", "p") == ""
