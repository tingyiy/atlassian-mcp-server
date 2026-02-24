"""Unit tests for mention resolution in server.py."""

import asyncio
import re
from unittest.mock import AsyncMock, patch

import pytest

# Import the pieces we need to test
from server import (
    _MENTION_PLACEHOLDER,
    _PLACEHOLDER_RE,
    _inject_mentions,
    _md_to_adf_with_mentions,
    _split_placeholders,
)


class TestMentionPlaceholder:
    """Tests for placeholder formatting and regex matching."""

    def test_placeholder_produces_valid_string(self):
        key = "id:712020:31fab665-25ec-419b-b49d-d11fdc4e672e"
        result = _MENTION_PLACEHOLDER % key
        assert result == "{{{MENTION:id:712020:31fab665-25ec-419b-b49d-d11fdc4e672e}}}"

    def test_placeholder_regex_matches_produced_placeholder(self):
        key = "id:712020:31fab665-25ec-419b-b49d-d11fdc4e672e"
        placeholder = _MENTION_PLACEHOLDER % key
        match = _PLACEHOLDER_RE.search(placeholder)
        assert match is not None
        assert match.group(1) == key

    def test_placeholder_with_name_key(self):
        key = "name:ryan.stomel"
        placeholder = _MENTION_PLACEHOLDER % key
        match = _PLACEHOLDER_RE.search(placeholder)
        assert match is not None
        assert match.group(1) == key

    def test_placeholder_in_surrounding_text(self):
        key = "id:abc123"
        text = f"Hello {_MENTION_PLACEHOLDER % key} how are you?"
        matches = list(_PLACEHOLDER_RE.finditer(text))
        assert len(matches) == 1
        assert matches[0].group(1) == key


class TestSplitPlaceholders:
    """Tests for _split_placeholders node splitting."""

    def test_single_mention_in_text(self):
        key = "id:abc123"
        resolved = {key: {"accountId": "abc123", "displayName": "Ryan Stomel"}}
        node = {"type": "text", "text": f"Hey {_MENTION_PLACEHOLDER % key} check this"}
        parts = _split_placeholders(node, resolved)

        assert len(parts) == 3
        assert parts[0] == {"type": "text", "text": "Hey "}
        assert parts[1] == {
            "type": "mention",
            "attrs": {"id": "abc123", "text": "@Ryan Stomel", "accessLevel": ""},
        }
        assert parts[2] == {"type": "text", "text": " check this"}

    def test_mention_at_start(self):
        key = "id:abc123"
        resolved = {key: {"accountId": "abc123", "displayName": "User"}}
        node = {"type": "text", "text": f"{_MENTION_PLACEHOLDER % key} hello"}
        parts = _split_placeholders(node, resolved)

        assert len(parts) == 2
        assert parts[0]["type"] == "mention"
        assert parts[1] == {"type": "text", "text": " hello"}

    def test_mention_at_end(self):
        key = "id:abc123"
        resolved = {key: {"accountId": "abc123", "displayName": "User"}}
        node = {"type": "text", "text": f"hello {_MENTION_PLACEHOLDER % key}"}
        parts = _split_placeholders(node, resolved)

        assert len(parts) == 2
        assert parts[0] == {"type": "text", "text": "hello "}
        assert parts[1]["type"] == "mention"

    def test_no_placeholder_returns_original(self):
        node = {"type": "text", "text": "no mentions here"}
        parts = _split_placeholders(node, {})
        assert parts == [node]

    def test_marks_preserved_on_surrounding_text(self):
        key = "id:abc123"
        resolved = {key: {"accountId": "abc123", "displayName": "User"}}
        marks = [{"type": "strong"}]
        node = {"type": "text", "text": f"bold {_MENTION_PLACEHOLDER % key} text", "marks": marks}
        parts = _split_placeholders(node, resolved)

        assert parts[0]["marks"] == marks
        assert "marks" not in parts[1]  # mention node has no marks
        assert parts[2]["marks"] == marks


class TestInjectMentions:
    """Tests for _inject_mentions ADF tree walking."""

    def test_injects_into_paragraph(self):
        key = "id:abc123"
        resolved = {key: {"accountId": "abc123", "displayName": "User"}}
        placeholder = _MENTION_PLACEHOLDER % key
        adf = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"Hello {placeholder}"}],
                }
            ],
        }
        _inject_mentions(adf, resolved)

        para_content = adf["content"][0]["content"]
        assert any(n.get("type") == "mention" for n in para_content)


class TestMdToAdfWithMentions:
    """Integration tests for _md_to_adf_with_mentions with mocked Jira."""

    @pytest.fixture(autouse=True)
    def mock_jira(self):
        """Patch the global jira client in server module."""
        mock = AsyncMock()
        with patch("server.jira", mock):
            self.jira_mock = mock
            yield

    def test_account_id_mention_resolves(self):
        account_id = "712020:31fab665-25ec-419b-b49d-d11fdc4e672e"
        self.jira_mock.get_user.return_value = {
            "accountId": account_id,
            "displayName": "Ryan Stomel",
        }

        result = asyncio.get_event_loop().run_until_complete(
            _md_to_adf_with_mentions(f"@[{account_id}] heads up, deploy is tomorrow.")
        )

        assert isinstance(result, dict), f"Expected ADF dict, got string: {result}"
        # Verify a mention node exists somewhere in the tree
        assert _find_mention_node(result, account_id)

    def test_invalid_account_id_returns_error_string(self):
        self.jira_mock.get_user.return_value = None

        result = asyncio.get_event_loop().run_until_complete(
            _md_to_adf_with_mentions("@[bogus-id] hello")
        )

        assert isinstance(result, str)
        assert "bogus-id" in result

    def test_ambiguous_name_returns_disambiguation(self):
        self.jira_mock.search_users.return_value = [
            {"accountId": "id1", "displayName": "Ryan Stomel"},
            {"accountId": "id2", "displayName": "Ryan Scott"},
        ]

        result = asyncio.get_event_loop().run_until_complete(
            _md_to_adf_with_mentions("@Ryan check this")
        )

        assert isinstance(result, str)
        assert "multiple matches" in result.lower()

    def test_unique_name_resolves(self):
        self.jira_mock.search_users.return_value = [
            {"accountId": "id1", "displayName": "UniqueUser"},
        ]

        result = asyncio.get_event_loop().run_until_complete(
            _md_to_adf_with_mentions("@UniqueUser check this")
        )

        assert isinstance(result, dict), f"Expected ADF dict, got string: {result}"
        assert _find_mention_node(result, "id1")

    def test_no_mentions_passes_through(self):
        result = asyncio.get_event_loop().run_until_complete(
            _md_to_adf_with_mentions("plain text, no mentions")
        )

        assert isinstance(result, dict)


def _find_mention_node(adf: dict, account_id: str) -> bool:
    """Recursively search ADF tree for a mention node with the given account ID."""
    if adf.get("type") == "mention" and adf.get("attrs", {}).get("id") == account_id:
        return True
    for child in adf.get("content", []):
        if _find_mention_node(child, account_id):
            return True
    return False
