"""One place for turning an HTTP error into a message a caller can act on.

`response.raise_for_status()` produces "Client error '400 Bad Request' for url
..." and throws the body away. For Atlassian that body is the whole diagnosis:
Jira answers a rejected create with `{"errorMessages": [...], "errors":
{"description": "..."}}` naming the exact invalid field, and Confluence does
the same. Without it a 400 on a long markdown description means bisecting the
input blind.

Keeps the exception type (`httpx.HTTPStatusError`) so any `except` upstream
still matches; only the message grows.
"""

import httpx

# Enough to carry Jira's error JSON in full; short enough that an HTML error
# page from a proxy does not flood a log line. A bound on ENCODED BYTES, not
# characters: slicing `response.text` looked the same but let a multibyte body
# (emoji, CJK) run several times past the promised size while the suffix still
# claimed "bytes" — Copilot, PR #4.
_BODY_LIMIT_BYTES = 2000


def _truncate(response: httpx.Response) -> str:
    # The bound protects whatever LOGS this message, and Python strings are
    # emitted as UTF-8 there — so it must be measured on the UTF-8 form of the
    # decoded text, not on the wire bytes. A 1,500-byte ISO-8859-1 body of `é`
    # is under the limit on the wire and 3,000 bytes once logged (Copilot, PR
    # #4). Decode first (httpx honours the response charset), then cut on the
    # UTF-8 encoding; errors="ignore" drops a character torn at the cut rather
    # than raising or emitting U+FFFD into an error message.
    text = (response.text or "").strip()
    encoded = text.encode("utf-8")
    if len(encoded) <= _BODY_LIMIT_BYTES:
        return text
    head = encoded[:_BODY_LIMIT_BYTES].decode("utf-8", errors="ignore").strip()
    return head + f"… [{len(response.content or b'')} bytes on the wire]"


def raise_for_status_with_body(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = _truncate(response)
        if not body:
            raise
        raise httpx.HTTPStatusError(
            f"{exc}\nResponse body: {body}",
            request=exc.request,
            response=exc.response,
        ) from None
