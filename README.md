# Atlassian MCP Server

<a href="https://glama.ai/mcp/servers/@tingyiy/atlassian-mcp-server">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@tingyiy/atlassian-mcp-server/badge" />
</a>

An MCP server for Jira and Confluence Cloud. Write in **markdown** — the server converts to Atlassian Document Format (ADF) automatically.

## Quickstart

```bash
git clone https://github.com/tingyiy/atlassian-mcp-server.git
cd atlassian-mcp-server
pip install -r requirements.txt   # or: uv pip install -r requirements.txt
```

Then add it to your MCP client (see [Configuration](#configuration) below).

You'll need an [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens) and these values:

| Variable | Example |
|----------|---------|
| `ATLASSIAN_USERNAME` | `you@company.com` |
| `ATLASSIAN_API_KEY` | your API token |
| `JIRA_URL` | `https://your-domain.atlassian.net/rest/api/3` |
| `CONFLUENCE_URL` | `https://your-domain.atlassian.net/wiki` |
| `CONFLUENCE_SPACE_KEY` | `ENG` (optional, default space) |

## Tools

### Jira

| Tool | Description |
|------|-------------|
| `list_jira_issues` | Search issues using JQL |
| `read_jira_issue` | Get full issue details |
| `jira_create_issue` | Create an issue (markdown description) |
| `jira_update_issue` | Update summary or description (markdown) |
| `jira_add_comment` | Add a comment (markdown) |
| `jira_get_comments` | Retrieve all comments |
| `jira_get_attachment_image` | Download an attachment by ID |
| `jira_transition_issue` | Move issue through workflow |
| `jira_get_transitions` | List available transitions |

### Confluence

| Tool | Description |
|------|-------------|
| `list_confluence_pages` | List pages in a space |
| `view_confluence_page` | Get page content and metadata |
| `confluence_create_page` | Create a page (optionally nested) |
| `edit_confluence_page` | Update a page (auto-increments version) |
| `confluence_delete_page` | Delete a page |
| `confluence_search` | Search using CQL |
| `confluence_get_comments` | Get all comments on a page |
| `confluence_add_comment` | Add a comment (with reply support) |
| `confluence_get_attachment_image` | Download an image attachment |

### Markdown Support

Jira tools (`jira_create_issue`, `jira_update_issue`, `jira_add_comment`) accept **markdown** for descriptions and comments. The server converts it to ADF behind the scenes using [md2adf](https://github.com/tingyiy/m2adf).

Supported formatting: headings, bold, italic, strikethrough, inline code, links, images, code blocks (with language), bullet/ordered/nested lists, blockquotes, horizontal rules, and tables.

## Configuration

### Claude Code

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "atlassian": {
      "type": "stdio",
      "command": "python3",
      "args": ["/path/to/atlassian-mcp-server/server.py"],
      "env": {
        "ATLASSIAN_USERNAME": "you@company.com",
        "ATLASSIAN_API_KEY": "your_api_token",
        "JIRA_URL": "https://your-domain.atlassian.net/rest/api/3",
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_SPACE_KEY": "ENG"
      }
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "atlassian": {
      "command": "python3",
      "args": ["/path/to/atlassian-mcp-server/server.py"],
      "env": {
        "ATLASSIAN_USERNAME": "you@company.com",
        "ATLASSIAN_API_KEY": "your_api_token",
        "JIRA_URL": "https://your-domain.atlassian.net/rest/api/3",
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_SPACE_KEY": "ENG"
      }
    }
  }
}
```

### Cursor / VS Code

Add to `.cursor/mcp.json` or `.vscode/mcp.json`:

```json
{
  "mcpServers": {
    "atlassian": {
      "command": "python3",
      "args": ["/path/to/atlassian-mcp-server/server.py"],
      "env": {
        "ATLASSIAN_USERNAME": "you@company.com",
        "ATLASSIAN_API_KEY": "your_api_token",
        "JIRA_URL": "https://your-domain.atlassian.net/rest/api/3",
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki"
      }
    }
  }
}
```

Make sure the `python3` in `command` points to an environment with the dependencies installed. To be explicit, use the full path (e.g. `/path/to/venv/bin/python`).

## Notes

### Mermaid Diagrams in Confluence

Confluence's Mermaid plugin stores diagram source internally, so the MCP tools can't render them programmatically. Instead, provide the Mermaid source in a code block — the user can then convert it in the Confluence editor.

## License

MIT — see [LICENSE](LICENSE).
