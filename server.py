from mcp.server.fastmcp import FastMCP
from jira_client import JiraClient
from confluence_client import ConfluenceClient
import logging
import sys
from typing import Any

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

@mcp.tool()
async def list_jira_issues(jql: str = "created is not empty order by created DESC", max_results: int = 50) -> str:
    """Lists Jira issues using JQL."""
    logger.info(f"Tool called: list_jira_issues(jql='{jql}', max_results={max_results})")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        issues = await jira.list_issues(jql, max_results)
        logger.info(f"Found {len(issues)} issues")
        return str(issues)
    except Exception as e:
        logger.error(f"Error listing issues: {e}")
        return f"Error: {e}"

@mcp.tool()
async def read_jira_issue(issue_key: str) -> str:
    """Gets details of a specific Jira issue."""
    logger.info(f"Tool called: read_jira_issue(issue_key='{issue_key}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        issue = await jira.get_issue(issue_key)
        logger.info(f"Successfully read issue {issue_key}")
        return str(issue)
    except Exception as e:
        logger.error(f"Error reading issue {issue_key}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def jira_add_comment(issue_key: str, comment: Any) -> str:
    """Adds a comment to a Jira issue. 
    Accepts a string (plain text) or a dictionary (Atlassian Document Format).
    """
    logger.info(f"Tool called: jira_add_comment(issue_key='{issue_key}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        result = await jira.add_comment(issue_key, comment)
        comment_id = result.get('id')
        logger.info(f"Comment added to {issue_key}, ID: {comment_id}")
        return f"Comment added. ID: {comment_id}"
    except Exception as e:
        logger.error(f"Error adding comment to {issue_key}: {e}")
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
async def jira_update_issue(issue_key: str, summary: str = None, description: Any = None) -> str:
    """Updates the summary or description of a Jira issue.
    For description, accepts a string (plain text) or a dictionary (Atlassian Document Format).
    """
    logger.info(f"Tool called: jira_update_issue(issue_key='{issue_key}', summary={'provided' if summary else 'None'}, description={'provided' if description else 'None'})")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    
    fields = {}
    if summary:
        fields["summary"] = summary
    if description:
        if isinstance(description, str):
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "text": description,
                                "type": "text"
                            }
                        ]
                    }
                ]
            }
        else:
            fields["description"] = description
    
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
async def jira_create_issue(project_key: str, summary: str, description: Any = None, issuetype: str = "Task") -> str:
    """Creates a new Jira issue.
    For description, accepts a string (plain text) or a dictionary (Atlassian Document Format).
    """
    logger.info(f"Tool called: jira_create_issue(project_key='{project_key}', summary='{summary}')")
    if not jira:
        logger.error("Jira client not initialized")
        return "Jira client not initialized. Check configuration."
    try:
        result = await jira.create_issue(project_key, summary, description, issuetype)
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

@mcp.tool()
async def edit_confluence_page(page_id: str, title: str, content: str, version: int = None) -> str:
    """Updates a Confluence page.
    If version is not provided, it will be automatically incremented.
    
    MERMAID DIAGRAMS:
    Confluence Cloud uses the Mermaid Diagrams plugin. You CANNOT create rendered diagrams programmatically.
    The mermaid-cloud macro only references diagram content in the plugin's internal storage (not accessible via API).
    
    To include a Mermaid diagram, provide it as a code block for the user to manually convert:
    <ac:structured-macro ac:name="code" ac:schema-version="1">
    <ac:parameter ac:name="language">text</ac:parameter>
    <ac:plain-text-body><![CDATA[sequenceDiagram
        participant A
        participant B
        A->>B: Request
        B-->>A: Response]]></ac:plain-text-body>
    </ac:structured-macro>
    
    The user can then convert this code block to a rendered diagram in the Confluence editor.
    """
    logger.info(f"Tool called: edit_confluence_page(page_id='{page_id}', version={version})")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        result = await confluence.update_page(page_id, title, content, version)
        logger.info(f"Page {page_id} updated successfully")
        return str(result)
    except Exception as e:
        logger.error(f"Error updating page {page_id}: {e}")
        return f"Error: {e}"

@mcp.tool()
async def confluence_create_page(title: str, content: str, parent_id: str = None, space_key: str = None) -> str:
    """Creates a new Confluence page, optionally under a parent page."""
    logger.info(f"Tool called: confluence_create_page(title='{title}', parent_id={parent_id}, space_key={space_key})")
    if not confluence:
        logger.error("Confluence client not initialized")
        return "Confluence client not initialized. Check configuration."
    try:
        result = await confluence.create_page(title, content, parent_id, space_key)
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

if __name__ == "__main__":
    mcp.run()
