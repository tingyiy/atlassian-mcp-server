# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Atlassian MCP Server — a Model Context Protocol server bridging LLMs with Jira and Confluence Cloud. Accepts markdown input and converts it to Atlassian Document Format (ADF) automatically via the [md2adf](https://github.com/tingyiy/m2adf) library.

## Commands

```bash
# Install dependencies (pyenv environment "atlassian-mcp")
pip install -r requirements.txt

# Run the MCP server (stdio transport)
python server.py

# Run unit tests (mention resolution)
python -m pytest test_mentions.py -v

# Run a single test
python -m pytest test_mentions.py::TestMentionPlaceholder::test_placeholder_produces_valid_string -v

# Run integration tests (requires valid .env credentials)
python test_integration.py
python test_jira_image.py
```

## Architecture

Three files form the core:

- **`server.py`** — FastMCP entry point. Registers all tool functions (`@mcp.tool()`), initializes clients globally, handles mention resolution. All tools are async. Logs to stderr to keep stdout clean for MCP protocol.
- **`jira_client.py`** — `JiraClient` class wrapping Jira REST API v3 with `httpx.AsyncClient`. Uses `POST /rest/api/3/search/jql` for searches (the GET endpoint is deprecated).
- **`confluence_client.py`** — `ConfluenceClient` class wrapping Confluence Cloud REST API with `httpx.AsyncClient`. Auto-increments page version on updates if not provided.

### Mention Resolution (server.py lines 37–195)

The most complex subsystem. Three-phase pipeline:

1. **Resolve** — Parses `@[accountId]` (direct) and `@username` (search-based) mentions. Validates IDs via `jira.get_user()`, searches names via `jira.search_users()`.
2. **Disambiguate** — If any `@username` matches multiple users, returns an error string (comment is NOT posted) asking the caller to retry with `@[accountId]`.
3. **Placeholder swap** — Replaces mentions with `{{{MENTION:key}}}` placeholders before ADF conversion (to prevent mistune from mangling bracket syntax), then walks the ADF tree to inject mention nodes. Preserves text formatting marks during splitting.

### Key Patterns

- All I/O is async (`httpx.AsyncClient`, `async def` tools)
- Auth: Basic Auth with email + API token, configured via `.env`
- Clients can be `None` if config is missing — server still starts but tools return error strings
- Jira tools that accept descriptions/comments run markdown through `_md_to_adf_with_mentions()` which returns either an ADF dict (success) or a string (disambiguation/error)
- Confluence tools pass raw content (XHTML storage format) directly — no ADF conversion

## Environment Variables

Required in `.env`:
- `ATLASSIAN_USERNAME` — Jira/Confluence user email
- `ATLASSIAN_API_KEY` — API token from Atlassian
- `JIRA_URL` — e.g. `https://domain.atlassian.net/rest/api/3`
- `CONFLUENCE_URL` — e.g. `https://domain.atlassian.net/wiki`
- `CONFLUENCE_SPACE_KEY` — optional default space key
