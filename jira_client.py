import os
import httpx
import base64
import logging
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("atlassian-mcp.jira")

class JiraClient:
    def __init__(self):
        self.base_url = os.getenv("JIRA_URL")
        self.username = os.getenv("ATLASSIAN_USERNAME")
        self.api_key = os.getenv("ATLASSIAN_API_KEY")
        
        if not all([self.base_url, self.username, self.api_key]):
            raise ValueError("Missing Jira configuration in .env")
            
        auth_str = f"{self.username}:{self.api_key}"
        self.auth_header = {
            "Authorization": f"Basic {base64.b64encode(auth_str.encode()).decode()}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def list_issues(self, jql: str = "created is not empty order by created DESC", next_page_token: Optional[str] = None, max_results: int = 50) -> Dict[str, Any]:
        logger.debug(f"list_issues: jql='{jql}', next_page_token={next_page_token}, max_results={max_results}")
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": ["key", "summary", "status", "priority", "assignee"]
        }
        if next_page_token:
            payload["nextPageToken"] = next_page_token
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/search/jql",
                json=payload,
                headers=self.auth_header
            )
            logger.debug(f"list_issues status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            
            issues = [
                {
                    "key": issue.get("key"),
                    "summary": (issue.get("fields") or {}).get("summary", "No Summary"),
                    "status": ((issue.get("fields") or {}).get("status") or {}).get("name", "Unknown"),
                    "priority": ((issue.get("fields") or {}).get("priority") or {}).get("name", "None"),
                    "assignee": ((issue.get("fields") or {}).get("assignee") or {}).get("displayName", "Unassigned")
                }
                for issue in data.get("issues", [])
            ]
            
            return {
                "issues": issues,
                "next_page_token": data.get("nextPageToken")
            }

    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/issue/{issue_key}",
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json()

    async def add_comment(self, issue_key: str, comment_body: Dict[str, Any]) -> Dict[str, Any]:
        """Adds a comment to an issue. Expects an ADF document dict."""
        async with httpx.AsyncClient() as client:
            payload = {"body": comment_body}
            response = await client.post(
                f"{self.base_url}/issue/{issue_key}/comment",
                json=payload,
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json()

    async def get_comments(self, issue_key: str) -> List[Dict[str, Any]]:
        """Gets all comments for an issue."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/issue/{issue_key}/comment",
                headers=self.auth_header
            )
            response.raise_for_status()
            data = response.json()
            return [
                {
                    "id": comment.get("id"),
                    "author": (comment.get("author") or {}).get("displayName", "Unknown"),
                    "created": comment.get("created"),
                    "body": comment.get("body")  # This is ADF format
                }
                for comment in data.get("comments", [])
            ]


    async def get_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        """Gets available transitions for an issue."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/issue/{issue_key}/transitions",
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json().get("transitions", [])

    async def transition_issue(self, issue_key: str, transition_id: str) -> None:
        """Transitions an issue to a new status."""
        async with httpx.AsyncClient() as client:
            payload = {
                "transition": {
                    "id": transition_id
                }
            }
            response = await client.post(
                f"{self.base_url}/issue/{issue_key}/transitions",
                json=payload,
                headers=self.auth_header
            )
            response.raise_for_status()

    async def get_attachment_content(self, attachment_id: str) -> Optional[Dict[str, Any]]:
        """Gets attachment content and metadata by ID.

        Returns dict with 'data' (bytes), 'filename', and 'mimeType', or None on failure.
        """
        async with httpx.AsyncClient() as client:
            meta_response = await client.get(
                f"{self.base_url}/attachment/{attachment_id}",
                headers=self.auth_header
            )
            meta_response.raise_for_status()
            metadata = meta_response.json()

            content_url = metadata.get("content")
            if not content_url:
                return None

            # Use separate headers for binary download: keep auth but
            # accept any content type and don't send Content-Type.
            download_headers = {
                "Authorization": self.auth_header["Authorization"],
                "Accept": "*/*",
            }
            response = await client.get(content_url, headers=download_headers, follow_redirects=True)
            response.raise_for_status()
            return {
                "data": response.content,
                "filename": metadata.get("filename", f"attachment_{attachment_id}"),
                "mimeType": metadata.get("mimeType", "application/octet-stream"),
            }


    async def update_issue(self, issue_key: str, fields: Dict[str, Any]) -> None:
        """Updates fields of an issue."""
        async with httpx.AsyncClient() as client:
            payload = {"fields": fields}
            response = await client.put(
                f"{self.base_url}/issue/{issue_key}",
                json=payload,
                headers=self.auth_header
            )
            response.raise_for_status()

    async def search_users(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search for Jira users by name or email."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/user/search",
                params={"query": query, "maxResults": max_results},
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json()

    async def create_issue(self, project_key: str, summary: str, description: Dict[str, Any] = None, issuetype: str = "Task") -> Dict[str, Any]:
        """Creates a new Jira issue. Description should be an ADF document dict."""
        async with httpx.AsyncClient() as client:
            fields = {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issuetype}
            }
            if description:
                fields["description"] = description

            payload = {"fields": fields}
            response = await client.post(
                f"{self.base_url}/issue",
                json=payload,
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json()
