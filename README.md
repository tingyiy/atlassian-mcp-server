# Atlassian MCP Server

<a href="https://glama.ai/mcp/servers/@tingyiy/atlassian-mcp-server">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@tingyiy/atlassian-mcp-server/badge" />
</a>


A Model Context Protocol (MCP) server that provides powerful tools for interacting with Atlassian Jira and Confluence Cloud. Built with Python and the `mcp` SDK.

This server enables LLM agents (like Claude Desktop) to:
- **Jira**: Search for issues using JQL, view issue details, add comments, transition issues, and create/update issues (with rich text support).
- **Confluence**: Search space content, view pages, create new pages (including nested pages), and edit pages (with auto-versioning).

## Features

### Jira Tools
- `list_jira_issues`: Search and list issues using JQL (Jira Query Language).
- `read_jira_issue`: Retrieve full details of a specific issue.
- `jira_create_issue`: Create new issues (Support for Projects, Issue Types, and ADF Descriptions).
- `jira_update_issue`: Update issue summary and description.
- `jira_add_comment`: Add comments to issues.
- `jira_get_comments`: Retrieve all comments on an issue.
- `jira_transition_issue`: Move issues through their workflow (e.g., To Do -> Done).

### Confluence Tools
- `list_confluence_pages`: List pages within a specific space.
- `view_confluence_page`: Retrieve page content and metadata.
- `confluence_create_page`: Create new pages, optionally nested under a parent page.
- `edit_confluence_page`: Update page content (Automatically handles version increments).
  - *Note*: Includes guidance for handling Mermaid diagrams via the Mermaid Diagrams plugin.
- `confluence_delete_page`: Delete a Confluence page.
- `confluence_search`: Perform advanced searches using CQL (Confluence Query Language).
- `confluence_get_comments`: Retrieve all comments on a page.

## Prerequisites

- **Python**: Version 3.10+ (Tested with 3.14.2)
- **Atlassian Account**: An Atlassian account with an API Token.

## Setup

1.  **Clone and Install**:
    ```bash
    git clone https://github.com/tingyiy/atlassian-mcp-server.git
    cd atlassian-mcp-server
    pip install -r requirements.txt
    ```

2.  **Configuration**:
    Create a `.env` file in the project root with your credentials:
    ```bash
    ATLASSIAN_USERNAME=your_email@example.com
    ATLASSIAN_API_KEY=your_api_token
    JIRA_URL=https://your-domain.atlassian.net/rest/api/3
    CONFLUENCE_URL=https://your-domain.atlassian.net/wiki
    CONFLUENCE_SPACE_KEY=your_default_space_key
    ```
    *Note: `JIRA_URL` must point to the `/rest/api/3` endpoint.*

3.  **Run the Server**:
    ```bash
    python server.py
    ```

## Usage

This MCP server can be used with any MCP-compliant client, including IDEs (like Cursor, VS Code) and desktop agents (like Claude Desktop).

### Generic Configuration
Most MCP clients require the command to run the server and the environment variables.
- **Command**: `python /abs/path/to/atlassian-mcp-server/server.py`
- **Environment**: All variables from `.env` must be passed to the process.

### Claude Desktop
Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "atlassian": {
      "command": "/path/to/python",
      "args": [
        "/path/to/atlassian-mcp-server/server.py"
      ],
      "env": {
        "ATLASSIAN_USERNAME": "your_email@example.com",
        "ATLASSIAN_API_KEY": "your_api_token",
        "JIRA_URL": "https://your-domain.atlassian.net/rest/api/3",
        "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki",
        "CONFLUENCE_SPACE_KEY": "DS"
      }
    }
  }
}
```

### Cursor
To use with Cursor (via the `.cursor/mcp.json` or settings):

```json
{
  "mcpServers": {
    "namd": "atlassian",
    "command": "python3",
    "args": ["/path/to/atlassian-mcp-server/server.py"],
    "env": {
      "ATLASSIAN_USERNAME": "your_email@example.com",
      "ATLASSIAN_API_KEY": "your_api_token",
      "JIRA_URL": "https://your-domain.atlassian.net/rest/api/3",
      "CONFLUENCE_URL": "https://your-domain.atlassian.net/wiki"
    }
  }
}
```
*Note: Ensure the python environment has the required dependencies installed.*

## Confluence Tips: Mermaid Diagrams

The MCP tools cannot render Mermaid diagrams programmatically because the standard plugin stores source code internally. To reference a diagram, provide the Mermaid source in a **code block** and ask the user to manually render it in the Confluence UI.

**Example Agent Output for a Diagram:**
"I've added the following code block to the page. Please select it in the editor and convert it to a Mermaid diagram:"
```html
<ac:structured-macro ac:name="code" ac:schema-version="1">
    <ac:parameter ac:name="language">text</ac:parameter>
    <ac:plain-text-body><![CDATA[graph TD; A-->B;]]></ac:plain-text-body>
</ac:structured-macro>
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1.  Fork the repository.
2.  Create your feature branch (`git checkout -b feature/AmazingFeature`).
3.  Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4.  Push to the branch (`git push origin feature/AmazingFeature`).
5.  Open a Pull Request.

## License

Distributed under the MIT License. See `LICENSE` for more information.
