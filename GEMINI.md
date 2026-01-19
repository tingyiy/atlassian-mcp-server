# Project Context: Atlassian MCP Server

## Project Overview & Goals
The Atlassian MCP Server is a Model Context Protocol (MCP) server designed to bridge LLMs with Atlassian's suite of tools: Jira and Confluence.
**Goals:**
- Provide efficient tools to list, read, and manage Jira issues.
- Enable searching, viewing, and editing of Confluence pages.
- Ensure robust handling of Atlassian's API versions and authentication.
- Maintain seamless integration with the `mcp` SDK for agentic workflows.

## Persona Definition
You are an expert Python developer and automation specialist, deeply familiar with the Model Context Protocol (MCP) and Atlassian REST APIs (Jira v3, Confluence Cloud). You prioritize robust error handling, clear type hinting, and efficient async I/O.

## Architecture & Key Files
The project is a standalone Python application located in `caeli/mcps/atlassian`.
- **`server.py`**: The main entry point initializing `FastMCP` and registering tools.
- **`jira_client.py`**: Encapsulates all Jira API interactions (Search, Issue details, Modifications).
- **`confluence_client.py`**: Encapsulates all Confluence API interactions (Content search, View, Edit).
- **`test_integration.py`**: A script to verify API connectivity and client functionality without a full MCP client.
- **`.env`**: Contains sensitive credentials (URL, User, API Key).
- **`requirements.txt`**: Project dependencies (`mcp`, `httpx`, `python-dotenv`).

## Setup & Execution
1.  **Environment**: Managed via `pyenv`.
    -   `pyenv local atlassian-mcp` (Python 3.14.2)
2.  **Dependencies**: `pip install -r requirements.txt`
3.  **Run Server**: `python server.py`
4.  **Test**: `python test_integration.py`

## Coding Standards
- **Language**: Python 3.14+
- **Style**: Follow PEP 8. Use strictly typed function signatures (`def func(a: int) -> str:`).
- **Libraries**:
    -   Use `httpx` for all HTTP requests (AsyncClient).
    -   Use `dotenv` for configuration.
    -   Use `mcp` SDK for server implementation.
- **Error Handling**: Raise informative errors or return clear error strings to the LLM. Handle optional fields in JSON responses gracefully (e.g., `(issue.get("fields") or {}).get("summary")`).

## Methodologies
- **Async First**: All I/O operations (API calls) must be asynchronous.
- **Robust Parsing**: APIs change (e.g., deprecations). Always verify payload structures and implement fail-safes for missing keys.
- **Verification**: Always verify changes using `test_integration.py` before finalizing.

## Project-Specific Rules
- **Jira API**: Use `POST /rest/api/3/search/jql` for searches. `GET /rest/api/3/search` is deprecated.
- **Confluence API**: Use the Cloud API format.
- **Auth**: Basic Auth with Email and API Token.

## Future Enhancements
### Jira Integration
- [x] **Create Issues**: Add a tool to create new Jira issues (`jira_create_issue`).
- [ ] **Comment Management**: Add tools to add and read comments on issues.
- [ ] **Transition Issues**: Add a tool to transition issue status (e.g., To Do -> In Progress).
- [ ] **Assignee Management**: Allow assigning issues to users.
- [ ] **Full Text Search**: Implement search using text query in addition to JQL.
- [ ] **Pagination**: Implement proper pagination for `list_issues` instead of just `max_results`.

### Confluence Integration
- [x] **Create Pages**: Add a tool to create new pages (`confluence_create_page`).
- [x] **Delete Pages**: Add a tool to delete specific pages (`confluence_delete_page`).
- [x] **Search CQL**: Expose full CQL (Confluence Query Language) search capabilities via `confluence_search`.
- [ ] **Comment Management**: Add tools to read and post comments on pages.
- [ ] **Attachment Handling**: Support downloading attachments (`jira_get_attachment_image`).

### General Improvements
- **Error Handling**: Improve error messages to be more user-friendly and handle specific Atlassian error codes more gracefully.
- **Caching**: Implement caching for frequently accessed resources (like user details or spaces) to reduce API calls.
- **Testing**: Add unit tests in addition to the integration tests.
- **Async Efficiency**: Optimize concurrent requests if bulk operations are added.
