"""ADF forbids the `code` mark beside a formatting mark on one text node.

md2adf flattens nested inline markup into a mark list, so "**a `b` c**" emits
marks [strong, code] and Jira rejects the entire payload with an opaque
400 INVALID_INPUT that names no construct (SCRUM-1333). Confirmed against the
REST API: code alone 201, strong alone 201, code+strong 400 in either order,
code+link 201. So `code` is not globally exclusive — only formatting marks are
the problem, and bold code is not representable in ADF at all.
"""
import os

import pytest

os.environ.setdefault("JIRA_URL", "https://x.atlassian.net/rest/api/3")
os.environ.setdefault("ATLASSIAN_USERNAME", "u@example.com")
os.environ.setdefault("ATLASSIAN_API_KEY", "not-a-real-key")
os.environ.setdefault("CONFLUENCE_URL", "https://x.atlassian.net/wiki")

from md2adf import convert as md_to_adf  # noqa: E402
from server import (  # noqa: E402
    _CODE_INCOMPATIBLE_MARKS,
    _sanitize_adf_marks,
    _wiki_markup_warning,
)


def _text_nodes(node, out=None):
    out = [] if out is None else out
    if isinstance(node, list):
        for child in node:
            _text_nodes(child, out)
    elif isinstance(node, dict):
        if node.get("type") == "text":
            out.append(node)
        _text_nodes(node.get("content", []), out)
    return out


def _mark_types(node):
    return {m["type"] for m in node.get("marks", [])}


def _illegal(adf):
    return [
        n for n in _text_nodes(adf)
        if "code" in _mark_types(n) and _mark_types(n) & _CODE_INCOMPATIBLE_MARKS
    ]


class TestSanitizer:
    @pytest.mark.parametrize("markdown", [
        "with **no `env` at all**",
        "a *ital `code` x* b",
        "~~strike `c` d~~",
        "- **bullet `code` here**",
        "| **cell `code`** |\n| --- |\n| x |",
        "# **heading `code`**",
        "> **quoted `code`**",
    ])
    def test_illegal_pair_is_removed(self, markdown):
        adf = md_to_adf(markdown)
        assert _illegal(adf), f"fixture no longer reproduces the bug: {markdown!r}"
        _sanitize_adf_marks(adf)
        assert not _illegal(adf)

    def test_code_survives_and_formatting_is_dropped(self):
        adf = md_to_adf("with **no `env` at all**")
        _sanitize_adf_marks(adf)
        env = [n for n in _text_nodes(adf) if n["text"] == "env"]
        assert len(env) == 1
        assert _mark_types(env[0]) == {"code"}

    def test_text_content_is_untouched(self):
        adf = md_to_adf("with **no `env` at all**")
        before = "".join(n["text"] for n in _text_nodes(adf))
        _sanitize_adf_marks(adf)
        assert "".join(n["text"] for n in _text_nodes(adf)) == before

    def test_returns_count_of_changed_nodes(self):
        adf = md_to_adf("**a `b` c** and **d `e` f**")
        assert _sanitize_adf_marks(adf) == 2
        assert _sanitize_adf_marks(adf) == 0  # idempotent

    def test_code_plus_link_is_left_alone(self):
        # code+link posts fine (201); stripping it would lose a real hyperlink.
        adf = {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "x", "marks": [
                {"type": "code"},
                {"type": "link", "attrs": {"href": "https://example.com"}},
            ]},
        ]}]}
        assert _sanitize_adf_marks(adf) == 0
        assert _mark_types(_text_nodes(adf)[0]) == {"code", "link"}

    def test_formatting_without_code_is_left_alone(self):
        adf = md_to_adf("***bold italic***")
        assert _sanitize_adf_marks(adf) == 0
        assert _mark_types(_text_nodes(adf)[0]) == {"strong", "em"}

    @pytest.mark.parametrize("other", sorted(_CODE_INCOMPATIBLE_MARKS))
    def test_every_incompatible_mark_is_stripped(self, other):
        adf = {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "x",
             "marks": [{"type": other}, {"type": "code"}]},
        ]}]}
        assert _sanitize_adf_marks(adf) == 1
        assert _mark_types(_text_nodes(adf)[0]) == {"code"}

    def test_mark_order_does_not_matter(self):
        # The API rejects both orders, so both must be sanitized.
        for marks in ([{"type": "code"}, {"type": "strong"}],
                      [{"type": "strong"}, {"type": "code"}]):
            adf = {"type": "doc", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "x", "marks": marks},
            ]}]}
            assert _sanitize_adf_marks(adf) == 1
            assert _mark_types(_text_nodes(adf)[0]) == {"code"}

    def test_survives_malformed_nodes(self):
        adf = {"type": "doc", "content": [
            {"type": "paragraph", "content": "not-a-list"},
            {"type": "text", "text": "x", "marks": "not-a-list"},
            {"type": "text", "text": "y", "marks": [None, "junk", {"type": "code"}]},
            None,
        ]}
        assert _sanitize_adf_marks(adf) == 0


class TestWikiMarkupWarning:
    @pytest.mark.parametrize("content,signal", [
        ("h2. Repro\nsome text", "h2."),
        ("{code:python}\nx = 1\n{code}", "{code:python}"),
        ("{noformat}raw{noformat}", "{noformat}"),
        ("{quote}said{quote}", "{quote}"),
        ("{panel:title=X}body{panel}", "{panel:title=X}"),
        ("{color:red}red{color}", "{color:red}"),
        ("intro\n\nh3. Later heading", "h3."),
    ])
    def test_wiki_markup_is_reported(self, content, signal):
        warning = _wiki_markup_warning(content)
        assert signal in warning
        assert "markdown only" in warning

    @pytest.mark.parametrize("content", [
        "",
        "## Real markdown heading\n\n```python\nx = 1\n```",
        "plain prose with no markup at all",
    ])
    def test_plain_markdown_is_silent(self, content):
        assert _wiki_markup_warning(content) == ""

    def test_none_is_silent(self):
        assert _wiki_markup_warning(None) == ""

    def test_h_prefixed_prose_is_not_flagged(self):
        assert _wiki_markup_warning("h2o. is not a heading") == ""
        assert _wiki_markup_warning("see section h2.3 below") == ""
