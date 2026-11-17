"""Exact yes/no routing (Fix 10)."""

import pytest

from app.chatbot.nl2sql import _is_yes


@pytest.mark.parametrize(
    "text, expected",
    [
        ("yesterday", False),
        ("Yes, this is exploratory", True),
        ("yes", True),
        ("true", True),
        ("y", True),
        ("no", False),
        (None, False),
        ("", False),
    ],
)
def test_is_yes_uses_a_word_boundary(text, expected):
    assert _is_yes(text) is expected
