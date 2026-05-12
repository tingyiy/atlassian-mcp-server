from mcp.server.fastmcp import FastMCP, Image
from jira_client import JiraClient
from confluence_client import ConfluenceClient
from md2adf import convert as md_to_adf
import json
import logging
import os
import re
import sys
import tempfile
from typing import Union

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("atlassian-mcp")

mcp = FastMCP("atlassian")

# Initialize clients lazily or globally? Globally is fine if env vars are present.
try:
    logger.info("Initializing Atlassian clients...")
    jira = JiraClient()
    confluence = ConfluenceClient()
    logger.info("Atlassian clients initialized successfully.")
except Exception as e:
    # If config is missing, tools might fail, but server should start?
    # Better to fail early if credentials are REQUIRED.
    logger.error(f"Error initializing clients: {e}")
    print(f"Error initializing clients: {e}", file=sys.stderr)
    # We'll allow server to start but tools will fail if clients aren't ready
    jira = None
    confluence = None

_MENTION_NAME_RE = re.compile(r'(?<!\w)@([a-zA-Z][a-zA-Z0-9._-]*)')
_MENTION_ID_RE = re.compile(r'@\[([^\]]+)\]')
_MENTION_PLACEHOLDER = '{{{MENTION:%s}}}'
_PLACEHOLDER_RE = re.compile(r'\{\{\{MENTION:([^}]+)\}\}\}')


async def _md_to_adf_with_mentions(markdown: str) -> dict | str:
    """Convert markdown to ADF, resolving @mentions to Jira users.

    Supports two formats:
    - @username — searches users; auto-resolves if exactly 1 match
    - @[accountId] — direct resolve by account ID (for retry after disambiguation)

    Returns ADF dict on success, or a disambiguation string if any
    @username matched multiple users (comment is NOT posted).
    """
    if not jira:
        return md_to_adf(markdown)

    # Phase 1: resolve all mentions
    resolved = {}   # key -> {accountId, displayName}
    ambiguous = []  # [(name, [users...])]

    # Direct ID references: @[accountId]
    invalid_ids = []
    for match in _MENTION_ID_RE.finditer(markdown):
        account_id = match.group(1)
        try:
            user = await jira.get_user(account_id)
        except Exception:
            user = None
        if user:
            key = f"id:{account_id}"
            resolved[key] = {
                "accountId": account_id,
                "displayName": user.get("displayName", "user"),
            }
        else:
            invalid_ids.append(account_id)

    if invalid_ids:
        lines = ["Could not find user(s) for the following account ID(s):\n"]
        for aid in invalid_ids:
            lines.append(f"  - @[{aid}]")
        lines.append("\nPlease verify the ID and try again. Use jira_search_users to look up users.")
        return "\n".join(lines)

    # Name-based mentions: @username
    seen = set()
    for match in _MENTION_NAME_RE.finditer(markdown):
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        try:
            users = await jira.search_users(name, max_results=5)
        except Exception:
            users = []

        if len(users) == 1:
            key = f"name:{name}"
            resolved[key] = {
                "accountId": users[0].get("accountId"),
                "displayName": users[0].get("displayName", name),
            }
        elif len(users) >= 2:
            ambiguous.append((name, users))

    # Phase 2: if any ambiguous, return disambiguation prompt
    if ambiguous:
        lines = ["Found multiple matches for the following mentions:\n"]
        for name, users in ambiguous:
            lines.append(f"@{name}:")
            for u in users:
                aid = u.get("accountId", "")
                dn = u.get("displayName", "")
                lines.append(f"  - {dn} → use @[{aid}]")
        lines.append(
            "\nPlease re-call with @[accountId] to specify the exact user."
        )
        return "\n".join(lines)

    # Phase 3: replace mentions in markdown with placeholders before ADF conversion
    # (so mistune doesn't mangle the @[id] brackets)
    processed = markdown
    for match in _MENTION_ID_RE.finditer(markdown):
        account_id = match.group(1)
        key = f"id:{account_id}"
        processed = processed.replace(match.group(0), _MENTION_PLACEHOLDER % key, 1)
    for name in seen:
        key = f"name:{name}"
        if key in resolved:
            processed = processed.replace(f"@{name}", _MENTION_PLACEHOLDER % key, 1)

    # Phase 4: convert to ADF
    adf = md_to_adf(processed)

    # Phase 5: walk ADF tree and swap placeholders for mention nodes
    if resolved:
        _inject_mentions(adf, resolved)
    return adf


def _inject_mentions(adf: dict, resolved: dict):
    """Walk ADF tree and replace placeholder text with mention nodes."""
    if "content" in adf:
        adf["content"] = _process_nodes(adf["content"], resolved)


def _process_nodes(content: list, resolved: dict) -> list:
    result = []
    for node in content:
        if node.get("type") == "text":
            result.extend(_split_placeholders(node, resolved))
        else:
            if "content" in node:
                node["content"] = _process_nodes(node["content"], resolved)
            result.append(node)
    return result


def _split_placeholders(node: dict, resolved: dict) -> list:
    text = node.get("text", "")
    marks = node.get("marks")
    parts = []
    last_end = 0

    for match in _PLACEHOLDER_RE.finditer(text):
        key = match.group(1)
        info = resolved.get(key)
        if not info:
            continue

        if match.start() > last_end:
            before = {"type": "text", "text": text[last_end:match.start()]}
            if marks:
                before["marks"] = marks
            parts.append(before)

        parts.append({
            "type": "mention",
            "attrs": {
                "id": info["accountId"],
                "text": f"@{info['displayName']}",
                "accessLevel": "",
            },
        })
        last_end = match.end()

    if not parts:
        return [node]

    if last_end < len(text):
        after = {"type": "text", "text": text[last_end:]}
        if marks:
            after["marks"] = marks
        parts.append(after)
    return parts


@mcp.tool()
async def jira_search_users(query: str, max_results: int = 10) -> str:
    """Searches for Jira users by name or email.

    Args:
        query: Name, email, or username fragment to search for.
        max_results: Maximum number of results to return.
    """
    logger.info(f"Tool called: jira_search_users(query='{query}', max_results={max_results})")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        users = await jira.search_users(query, max_results)
        simple = [
            {
                "accountId": u.get("accountId"),
                "displayName": u.get("displayName"),
                "emailAddress": u.get("emailAddress"),
                "active": u.get("active"),
            }
            for u in users
        ]
        logger.info(f"Found {len(simple)} users for query '{query}'")
        return json.dumps(simple, indent=2)
    except Exception as e:
        logger.error(f"Error searching users: {e}")
        return f"Error: {e}"


@mcp.tool()
async def list_jira_issues(jql: str = "created is not empty order by created DESC", next_page_token: str = None, max_results: int = 50, additional_fields: list[str] = None) -> str:
    """Lists Jira issues using JQL.

    By default returns key, summary, status, priority, assignee.
    Use additional_fields to include extra Jira fields in the response.

    Args:
        jql: JQL query string.
        next_page_token: Token for pagination (returned in previous response).
        max_results: Maximum number of results to return.
        additional_fields: Extra Jira field names to include, e.g.
            ["issuetype", "labels", "created", "updated", "duedate",
             "components", "fixVersions", "reporter", "resolution",
             "parent", "subtasks"].
    """
    logger.info(f"Tool called: list_jira_issues(jql='{jql}', next_page_token={next_page_token}, max_results={max_results}, additional_fields={additional_fields})")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        result = await jira.list_issues(jql, next_page_token, max_results, additional_fields)
        logger.info(f"Found {len(result['issues'])} issues")
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error listing issues: {e}")
        return f"Error: {e}"

@mcp.tool()
async def read_jira_issue(issue_key: str, additional_fields: list[str] = None) -> str:
    """Gets details of a specific Jira issue.

    By default returns a compact set of fields. Use additional_fields to
    request more without bloating every response.

    Args:
        issue_key: The issue key (e.g. "PROJ-123").
        additional_fields: Extra Jira field names to include, e.g.
            ["components", "fixVersions", "duedate", "resolution",
             "parent", "subtasks", "issuetype", "customfield_XXXXX"].
    """
    logger.info(f"Tool called: read_jira_issue(issue_key='{issue_key}', additional_fields={additional_fields})")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        issue = await jira.get_issue(issue_key)
        fields = issue.get("fields") or {}

        result = {
            "key": issue.get("key"),
            "summary": fields.get("summary"),
            "status": (fields.get("status") or {}).get("name"),
            "priority": (fields.get("priority") or {}).get("name"),
            "assignee": (fields.get("assignee") or {}).get("displayName"),
            "reporter": (fields.get("reporter") or {}).get("displayName"),
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "description": fields.get("description"),  # ADF format
            "labels": fields.get("labels", []),
            "attachments": [
                {
                    "id": a.get("id"),
                    "filename": a.get("filename"),
                    "mimeType": a.get("mimeType"),
                    "size": a.get("size")
                }
                for a in fields.get("attachment", [])
            ],
            "comment_count": (fields.get("comment") or {}).get("total", 0),
        }

        for f in (additional_fields or []):
            result[f] = fields.get(f)

        logger.info(f"Successfully read issue {issue_key}")
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error reading issue {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_list_fields() -> str:
    """Lists all available Jira fields (standard and custom).

    Use this to discover field IDs you can pass as additional_fields to
    read_jira_issue, list_jira_issues, or jira_update_issue.
    """
    logger.info("Tool called: jira_list_fields()")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        fields = await jira.get_fields()
        result = [
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "custom": f.get("custom", False),
            }
            for f in fields
        ]
        result.sort(key=lambda x: (x["custom"], x["name"] or ""))
        logger.info(f"Found {len(result)} fields")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error listing fields: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_add_comment(issue_key: str, comment: str) -> str:
    """Adds a comment to a Jira issue.

    Args:
        issue_key: The ID or key of the issue.
        comment: The comment content in markdown. Supports headings, bold,
            italic, strikethrough, links, code blocks, lists, tables, etc.

    Mentioning users:
        To tag a user, first call jira_search_users to find their accountId,
        then use @[accountId] in the text (e.g. @[712020:abc123]).
        You can also use @username which auto-resolves if there is exactly
        one match, but will fail if ambiguous — prefer @[accountId].
    """
    logger.info(f"Tool called: jira_add_comment(issue_key='{issue_key}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        adf = await _md_to_adf_with_mentions(comment)
        if isinstance(adf, str):
            return adf  # disambiguation needed
        result = await jira.add_comment(issue_key, adf)
        comment_id = result.get('id')
        logger.info(f"Comment added to {issue_key}, ID: {comment_id}")
        return f"Comment added. ID: {comment_id}"
    except Exception as e:
        logger.error(f"Error adding comment to {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_edit_comment(issue_key: str, comment_id: str, comment: str) -> str:
    """Edits an existing comment on a Jira issue.

    Args:
        issue_key: The ID or key of the issue.
        comment_id: The ID of the comment to edit (from jira_get_comments).
        comment: The new comment content in markdown. Supports headings, bold,
            italic, strikethrough, links, code blocks, lists, tables, etc.

    Mentioning users:
        To tag a user, first call jira_search_users to find their accountId,
        then use @[accountId] in the text (e.g. @[712020:abc123]).
        You can also use @username which auto-resolves if there is exactly
        one match, but will fail if ambiguous -- prefer @[accountId].
    """
    logger.info(f"Tool called: jira_edit_comment(issue_key='{issue_key}', comment_id='{comment_id}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        adf = await _md_to_adf_with_mentions(comment)
        if isinstance(adf, str):
            return adf  # disambiguation needed
        result = await jira.update_comment(issue_key, comment_id, adf)
        logger.info(f"Comment {comment_id} updated on {issue_key}")
        return f"Comment {comment_id} updated."
    except Exception as e:
        logger.error(f"Error editing comment {comment_id} on {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_delete_comment(issue_key: str, comment_id: str) -> str:
    """Deletes a comment from a Jira issue.

    Args:
        issue_key: The ID or key of the issue.
        comment_id: The ID of the comment to delete (from jira_get_comments).
    """
    logger.info(f"Tool called: jira_delete_comment(issue_key='{issue_key}', comment_id='{comment_id}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        await jira.delete_comment(issue_key, comment_id)
        logger.info(f"Comment {comment_id} deleted from {issue_key}")
        return f"Comment {comment_id} deleted."
    except Exception as e:
        logger.error(f"Error deleting comment {comment_id} on {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_transition_issue(issue_key: str, transition_id: str) -> str:
    """Transitions a Jira issue to a new status using a transition ID.
    Use jira_get_transitions to find available transition IDs.
    """
    logger.info(f"Tool called: jira_transition_issue(issue_key='{issue_key}', transition_id='{transition_id}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        await jira.transition_issue(issue_key, transition_id)
        logger.info(f"Issue {issue_key} transitioned successfully")
        return f"Issue {issue_key} transitioned successfully."
    except Exception as e:
        logger.error(f"Error transitioning issue {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_get_transitions(issue_key: str) -> str:
    """Gets available transitions for a Jira issue."""
    logger.info(f"Tool called: jira_get_transitions(issue_key='{issue_key}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        transitions = await jira.get_transitions(issue_key)
        # Simplify output for LLM
        simple_transitions = [{"id": t["id"], "name": t["name"], "to": t["to"]["name"]} for t in transitions]
        logger.info(f"Found {len(transitions)} transitions for {issue_key}")
        return str(simple_transitions)
    except Exception as e:
        logger.error(f"Error getting transitions for {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_update_issue(issue_key: str, summary: str = None, description: str = None, additional_fields: dict = None, rich_text_fields: dict = None) -> str:
    """Updates fields on a Jira issue.

    Args:
        issue_key: The issue key (e.g. "PROJ-123").
        summary: New summary text.
        description: New description in markdown. Supports headings, bold,
            italic, strikethrough, links, code blocks, lists, tables, etc.
        additional_fields: Dict of field_id -> value for simple fields
            (plain text, dates, numbers, selects).
            Use jira_list_fields to discover field IDs.
            Example: {"duedate": "2026-04-01", "labels": ["bug"]}
        rich_text_fields: Dict of field_id -> markdown string for rich text
            fields that need ADF conversion (e.g. Developer Notes,
            Deployment Info). These get converted to Atlassian Document
            Format automatically.
            Example: {"customfield_10402": "## Plan\n- Step 1\n- Step 2"}

    Mentioning users (in description and rich_text_fields):
        First call jira_search_users to find the accountId,
        then use @[accountId] in the text (e.g. @[712020:abc123]).
    """
    logger.info(f"Tool called: jira_update_issue(issue_key='{issue_key}', summary={'provided' if summary else 'None'}, description={'provided' if description else 'None'}, additional_fields={additional_fields}, rich_text_fields={rich_text_fields})")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."

    fields = {}
    if summary:
        fields["summary"] = summary
    if description:
        adf = await _md_to_adf_with_mentions(description)
        if isinstance(adf, str):
            return adf  # disambiguation needed
        fields["description"] = adf
    if additional_fields:
        fields.update(additional_fields)
    if rich_text_fields:
        for field_id, markdown in rich_text_fields.items():
            adf = await _md_to_adf_with_mentions(markdown)
            if isinstance(adf, str):
                return adf  # disambiguation needed
            fields[field_id] = adf

    if not fields:
        logger.warning(f"jira_update_issue called with no fields for {issue_key}")
        return "No fields provided to update."

    try:
        await jira.update_issue(issue_key, fields)
        logger.info(f"Issue {issue_key} updated")
        return f"Issue {issue_key} updated."
    except Exception as e:
        logger.error(f"Error updating issue {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_create_issue(project_key: str, summary: str, description: str = None, issuetype: str = "Task") -> str:
    """Creates a new Jira issue.
    For description, accepts a markdown string. Supports headings, bold,
    italic, strikethrough, links, code blocks, lists, tables, etc.

    Mentioning users:
        To tag a user, first call jira_search_users to find their accountId,
        then use @[accountId] in the text (e.g. @[712020:abc123]).
        You can also use @username which auto-resolves if there is exactly
        one match, but will fail if ambiguous — prefer @[accountId].
    """
    logger.info(f"Tool called: jira_create_issue(project_key='{project_key}', summary='{summary}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        adf_desc = None
        if description:
            adf_desc = await _md_to_adf_with_mentions(description)
            if isinstance(adf_desc, str):
                return adf_desc  # disambiguation needed
        result = await jira.create_issue(project_key, summary, adf_desc, issuetype)
        logger.info(f"Issue created: {result.get('key')}")
        return f"Issue created successfully. Key: {result.get('key')}, ID: {result.get('id')}"
    except Exception as e:
        logger.error(f"Error creating issue: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_get_comments(issue_key: str) -> str:
    """Gets all comments for a Jira issue."""
    logger.info(f"Tool called: jira_get_comments(issue_key='{issue_key}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        comments = await jira.get_comments(issue_key)
        return json.dumps(comments, indent=2)
    except Exception as e:
        logger.error(f"Error getting comments for {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_download_attachment(attachment_id: str) -> str:
    """Downloads a Jira attachment by ID, saves it to a temp file, and returns the file path."""
    logger.info(f"Tool called: jira_download_attachment(attachment_id='{attachment_id}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        result = await jira.get_attachment_content(attachment_id)
        if not result:
            return f"Error: Attachment {attachment_id} could not be downloaded."

        tmp_dir = os.path.join(tempfile.gettempdir(), "jira_attachments")
        os.makedirs(tmp_dir, exist_ok=True)

        filename = result["filename"]
        file_path = os.path.join(tmp_dir, f"{attachment_id}_{filename}")
        with open(file_path, "wb") as f:
            f.write(result["data"])

        mime = result["mimeType"]
        logger.info(f"Saved attachment to {file_path} ({mime}, {len(result['data'])} bytes)")

        return f"Attachment saved to {file_path} ({mime}, {len(result['data'])} bytes). Use the Read tool to view its contents."
    except Exception as e:
        logger.error(f"Error getting attachment {attachment_id}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_add_attachment(issue_key: str, file_path: str) -> str:
    """Uploads a file as an attachment to a Jira issue.

    Args:
        issue_key: The issue key (e.g. "PROJ-123").
        file_path: Absolute path to the file to upload.
    """
    logger.info(f"Tool called: jira_add_attachment(issue_key='{issue_key}', file_path='{file_path}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    file_path = os.path.expanduser(file_path)
    if not os.path.isfile(file_path):
        import glob as _glob
        pattern = file_path.replace(" ", "?")
        matches = _glob.glob(pattern)
        if len(matches) == 1:
            file_path = matches[0]
        else:
            return f"Error: File not found at {file_path}"
    try:
        result = await jira.add_attachment(issue_key, file_path)
        filenames = [a.get("filename", "unknown") for a in result] if isinstance(result, list) else [result.get("filename", "unknown")]
        return f"Attachment(s) uploaded successfully: {', '.join(filenames)}"
    except Exception as e:
        logger.error(f"Error uploading attachment to {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def list_confluence_pages(space_key: str = None, limit: int = 25) -> str:
    """Lists Confluence pages in a space."""
    logger.info(f"Tool called: list_confluence_pages(space_key='{space_key}', limit={limit})")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        pages = await confluence.list_pages(space_key, limit)
        logger.info(f"Found {len(pages)} pages")
        return str(pages)
    except Exception as e:
        logger.error(f"Error listing confluence pages: {e}")
        return f"Error: {e}"

@mcp.tool()
async def view_confluence_page(page_id: str) -> str:
    """Gets the content of a Confluence page."""
    logger.info(f"Tool called: view_confluence_page(page_id='{page_id}')")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        page = await confluence.get_page(page_id)
        logger.info(f"Successfully retrieved page {page_id}")
        return str(page)
    except Exception as e:
        logger.error(f"Error viewing page {page_id}: {e}")
        return f"Error: {e}"

_CONFLUENCE_FORMATS = ("markdown", "storage")

# Signals that content is Confluence storage XHTML rather than markdown.
# `<ac:` / `<ri:` are Confluence-specific namespaces (100% storage). The
# structural tags don't appear in normal markdown source — seeing them means
# the caller is sending storage XHTML through the markdown path, which md2adf
# would silently encode as literal text.
_XHTML_STORAGE_SIGNALS = re.compile(
    r'<ac:|<ri:|</?(?:h[1-6]|table|tbody|thead|tr|td|th)\b',
    re.IGNORECASE,
)

# Storage XHTML must contain at least one well-formed opening tag (`<` followed
# by an ASCII letter). Markdown source has no such tags — sending it as storage
# results in Confluence escaping the stray `<` chars and storing the whole
# document as literal text.
_STORAGE_OPENING_TAG = re.compile(r'<[a-zA-Z]')


def _confluence_body(content: str, content_format: str) -> Union[str, dict]:
    """Build the page body for Confluence based on the declared format.

    - "markdown" → convert to ADF (sent as atlas_doc_format)
    - "storage"  → pass XHTML through unchanged (sent as storage)
    Raises ValueError on an unknown format, on markdown content that contains
    Confluence storage XHTML markers, or on storage content that contains no
    XHTML tags at all.
    """
    if content_format == "markdown":
        match = _XHTML_STORAGE_SIGNALS.search(content)
        if match:
            raise ValueError(
                f"content looks like Confluence storage XHTML (found {match.group(0)!r}) "
                "but content_format is 'markdown'. Pass content_format='storage' to send "
                "raw XHTML, or convert the content to markdown."
            )
        return md_to_adf(content)
    if content_format == "storage":
        if not _STORAGE_OPENING_TAG.search(content):
            raise ValueError(
                "content_format is 'storage' but content has no XHTML opening tags. "
                "If this is markdown, pass content_format='markdown' (the default). "
                "If it is plain text, wrap it in <p>...</p>."
            )
        return content
    raise ValueError(
        f"Unknown content_format {content_format!r}. Expected one of: {', '.join(_CONFLUENCE_FORMATS)}"
    )


@mcp.tool()
async def edit_confluence_page(page_id: str, title: str, content: str, version: int = None, content_format: str = "markdown") -> str:
    """Updates a Confluence page.
    If version is not provided, it will be automatically incremented.

    content_format:
    - "markdown" (default) — content is converted to ADF before upload.
    - "storage" — content is sent as raw XHTML storage format. Use this to
      embed Confluence macros like `<ac:structured-macro>`.

    MERMAID DIAGRAMS:
    Confluence Cloud's Mermaid Diagrams plugin cannot be rendered via API.
    Provide diagrams as a fenced ```mermaid code block; the user can convert
    it to a rendered diagram in the Confluence editor.
    """
    logger.info(f"Tool called: edit_confluence_page(page_id='{page_id}', version={version}, content_format='{content_format}')")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        body = _confluence_body(content, content_format)
    except ValueError as e:
        logger.error(f"Invalid content_format: {e}")
        return f"Error: {e}"
    try:
        result = await confluence.update_page(page_id, title, body, version)
        logger.info(f"Page {page_id} updated successfully")
        return str(result)
    except Exception as e:
        logger.error(f"Error updating page {page_id}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def confluence_create_page(title: str, content: str, parent_id: str = None, space_key: str = None, content_format: str = "markdown") -> str:
    """Creates a new Confluence page, optionally under a parent page.

    content_format:
    - "markdown" (default) — content is converted to ADF before upload.
    - "storage" — content is sent as raw XHTML storage format (for macros etc.).
    """
    logger.info(f"Tool called: confluence_create_page(title='{title}', parent_id={parent_id}, space_key={space_key}, content_format='{content_format}')")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        body = _confluence_body(content, content_format)
    except ValueError as e:
        logger.error(f"Invalid content_format: {e}")
        return f"Error: {e}"
    try:
        result = await confluence.create_page(title, body, parent_id, space_key)
        page_id = result.get('id')
        logger.info(f"Page created successfully: {page_id}")
        return f"Page created successfully. ID: {page_id}, Link: {result.get('_links', {}).get('base')}{result.get('_links', {}).get('webui')}"
    except Exception as e:
        logger.error(f"Error creating page: {e}")
        return f"Error: {e}"

@mcp.tool()
async def confluence_delete_page(page_id: str) -> str:
    """Deletes a Confluence page."""
    logger.info(f"Tool called: confluence_delete_page(page_id='{page_id}')")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        await confluence.delete_page(page_id)
        logger.info(f"Page {page_id} deleted successfully")
        return f"Page {page_id} deleted successfully."
    except Exception as e:
        logger.error(f"Error deleting page {page_id}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def confluence_search(cql: str, limit: int = 25) -> str:
    """Searches Confluence content using CQL (Confluence Query Language).
    Example: title ~ "meeting" AND label = "notes"
    """
    logger.info(f"Tool called: confluence_search(cql='{cql}', limit={limit})")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        results = await confluence.search(cql, limit)
        return json.dumps(results, indent=2)
    except Exception as e:
        logger.error(f"Error searching Confluence: {e}")
        return f"Error: {e}"

@mcp.tool()
async def confluence_get_comments(page_id: str) -> str:
    """Gets all comments for a Confluence page."""
    logger.info(f"Tool called: confluence_get_comments(page_id='{page_id}')")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        comments = await confluence.get_comments(page_id)
        return json.dumps(comments, indent=2)
    except Exception as e:
        logger.error(f"Error getting comments for page {page_id}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def confluence_add_comment(page_id: str, body: str, parent_comment_id: str = None) -> str:
    """Adds a comment to a Confluence page. 
    Set parent_comment_id to reply to an existing comment.
    """
    logger.info(f"Tool called: confluence_add_comment(page_id='{page_id}', parent_comment_id={parent_comment_id})")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        result = await confluence.add_comment(page_id, body, parent_comment_id)
        comment_id = result.get('id')
        logger.info(f"Comment added: {comment_id}")
        return f"Comment added successfully. ID: {comment_id}"
    except Exception as e:
        logger.error(f"Error adding comment to page {page_id}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def confluence_get_attachment_image(page_id: str, filename: str) -> Image:
    """Gets an image attachment on a Confluence page and returns it as an Image."""
    logger.info(f"Tool called: confluence_get_attachment_image(page_id='{page_id}', filename='{filename}')")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        image_data = await confluence.get_attachment_image(page_id, filename)
        if not image_data:
            return f"Error: Attachment '{filename}' not found on page {page_id}."
            
        return Image(data=image_data, format='png')
    except Exception as e:
        logger.error(f"Error getting attachment {filename} from page {page_id}: {e}")
        return f"Error: {e}"

if __name__ == "__main__":
    mcp.run()
