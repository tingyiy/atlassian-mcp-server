"""A rejected Atlassian request must surface the response body.

`raise_for_status()` discards it, and for Jira that body is the diagnosis —
`errors.description` names the exact invalid field. Reproduced 2026-09-02:
a create_issue 400 came back as a bare "400 Bad Request" and took four rounds
of blind bisecting to work around.
"""
import os

import httpx
import pytest

os.environ.setdefault("JIRA_URL", "https://x.atlassian.net/rest/api/3")
os.environ.setdefault("ATLASSIAN_USERNAME", "u@example.com")
os.environ.setdefault("ATLASSIAN_API_KEY", "not-a-real-key")
os.environ.setdefault("CONFLUENCE_URL", "https://x.atlassian.net/wiki")

from _http import raise_for_status_with_body  # noqa: E402
import jira_client  # noqa: E402
import confluence_client  # noqa: E402

JIRA_400 = (
    '{"errorMessages":[],"errors":{"description":'
    '"Operation value must be an Atlassian Document (see the Atlassian Document Format)"}}'
)


def _resp(status, body, url="https://x.atlassian.net/rest/api/3/issue"):
    req = httpx.Request("POST", url)
    return httpx.Response(status, content=body.encode(), request=req)


def test_error_message_carries_the_body():
    with pytest.raises(httpx.HTTPStatusError) as ei:
        raise_for_status_with_body(_resp(400, JIRA_400))
    msg = str(ei.value)
    assert "400" in msg
    assert "Operation value must be an Atlassian Document" in msg, msg
    assert "errors" in msg


def test_type_is_unchanged_so_existing_excepts_still_match():
    with pytest.raises(httpx.HTTPStatusError):
        raise_for_status_with_body(_resp(403, '{"errorMessages":["forbidden"]}'))


def test_empty_body_falls_back_to_the_plain_error():
    with pytest.raises(httpx.HTTPStatusError) as ei:
        raise_for_status_with_body(_resp(502, ""))
    assert "Response body" not in str(ei.value)


def test_huge_body_is_truncated_not_dropped():
    with pytest.raises(httpx.HTTPStatusError) as ei:
        raise_for_status_with_body(_resp(500, "<html>" + "x" * 10_000))
    msg = str(ei.value)
    assert "<html>" in msg
    assert "bytes total" in msg
    assert len(msg) < 3000


def test_success_is_a_no_op():
    raise_for_status_with_body(_resp(201, '{"key":"SCRUM-1"}'))


@pytest.mark.asyncio
async def test_create_issue_surfaces_jiras_diagnosis(monkeypatch):
    """End to end through the real JiraClient, with httpx's MockTransport
    standing in for Atlassian — no monkeypatching of client internals."""
    def handler(request):
        return httpx.Response(400, content=JIRA_400.encode(), request=request)
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **k: real(transport=httpx.MockTransport(handler)))
    client = jira_client.JiraClient()
    with pytest.raises(httpx.HTTPStatusError) as ei:
        await client.create_issue("SCRUM", "x", description={"type": "doc"})
    assert "Operation value must be an Atlassian Document" in str(ei.value), str(ei.value)


@pytest.mark.asyncio
async def test_confluence_search_surfaces_the_body_too(monkeypatch):
    """Same class of bug in the sibling client; fixed together."""
    def handler(request):
        return httpx.Response(400, content=b'{"message":"CQL: unexpected token"}', request=request)
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda *a, **k: real(transport=httpx.MockTransport(handler)))
    client = confluence_client.ConfluenceClient()
    with pytest.raises(httpx.HTTPStatusError) as ei:
        await client.search("bad cql")
    assert "CQL: unexpected token" in str(ei.value), str(ei.value)


def test_limit_is_on_encoded_bytes_not_characters():
    """Copilot, PR #4: slicing characters let a multibyte body run several
    times past the promised 2 KB while the suffix still said 'bytes'."""
    emoji_body = "🔥" * 1500          # 1500 chars, 6000 bytes in UTF-8
    with pytest.raises(httpx.HTTPStatusError) as ei:
        raise_for_status_with_body(_resp(500, emoji_body))
    msg = str(ei.value)
    payload = msg.split("Response body: ", 1)[1]
    head = payload.split("… [")[0]
    assert len(head.encode("utf-8")) <= 2000, len(head.encode("utf-8"))
    assert "[6000 bytes total]" in msg, msg
    assert "�" not in msg, "a torn character must be dropped, not replaced"


def test_short_multibyte_body_is_not_truncated():
    body = "描述字段无效 — 需要 ADF 文档"    # well under 2 KB in bytes
    with pytest.raises(httpx.HTTPStatusError) as ei:
        raise_for_status_with_body(_resp(400, body))
    assert body in str(ei.value)
    assert "bytes total" not in str(ei.value)
