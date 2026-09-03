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
# page from a proxy does not flood a log line.
_BODY_LIMIT = 2000


def raise_for_status_with_body(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = (response.text or "").strip()
        if not body:
            raise
        if len(body) > _BODY_LIMIT:
            body = body[:_BODY_LIMIT] + f"… [{len(response.text)} bytes total]"
        raise httpx.HTTPStatusError(
            f"{exc}\nResponse body: {body}",
            request=exc.request,
            response=exc.response,
        ) from None
