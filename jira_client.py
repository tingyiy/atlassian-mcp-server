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

    async def list_issues(self, jql: str = "created is not empty order by created DESC", max_results: int = 50) -> List[Dict[str, Any]]:
        logger.debug(f"list_issues: jql='{jql}'")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/search/jql",
                json={
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": ["key", "summary", "status", "priority", "assignee"]
                },
                headers=self.auth_header
            )
            logger.debug(f"list_issues status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            # print("DEBUG:", data)
            return [
                {
                    "key": issue.get("key"),
                    "summary": (issue.get("fields") or {}).get("summary", "No Summary"),
                    "status": ((issue.get("fields") or {}).get("status") or {}).get("name", "Unknown"),
                    "priority": ((issue.get("fields") or {}).get("priority") or {}).get("name", "None"),
                    "assignee": ((issue.get("fields") or {}).get("assignee") or {}).get("displayName", "Unassigned")
                }
                for issue in data.get("issues", [])
            ]

    async def get_issue(self, issue_key: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/issue/{issue_key}",
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json()

    async def add_comment(self, issue_key: str, comment_body: Any) -> Dict[str, Any]:
        """Adds a comment to an issue."""
        async with httpx.AsyncClient() as client:
            if isinstance(comment_body, str):
                payload = {
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "text": comment_body,
                                        "type": "text"
                                    }
                                ]
                            }
                        ]
                    }
                }
            else:
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

    async def download_attachment(self, attachment_id: str) -> Optional[bytes]:
        """Downloads an attachment by ID."""
        async with httpx.AsyncClient() as client:
            # The standard endpoint for content is /rest/api/3/attachment/content/{id}
            # However, sometimes we need to follow the 'content' link from metadata.
            # But usually, directly accessing the content URL works if we know the ID.
            # The robust way: GET /rest/api/3/attachment/{id} to get metadata (including secure content URL)
            
            meta_response = await client.get(
                f"{self.base_url}/attachment/{attachment_id}",
                headers=self.auth_header
            )
            meta_response.raise_for_status()
            metadata = meta_response.json()
            
            content_url = metadata.get("content")
            if not content_url:
                return None
                
            img_response = await client.get(content_url, headers=self.auth_header, follow_redirects=True)
            img_response.raise_for_status()
            return img_response.content


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

    async def create_issue(self, project_key: str, summary: str, description: Any = None, issuetype: str = "Task") -> Dict[str, Any]:
        """Creates a new Jira issue."""
        async with httpx.AsyncClient() as client:
            fields = {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issuetype}
            }
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
            
            payload = {"fields": fields}
            response = await client.post(
                f"{self.base_url}/issue",
                json=payload,
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json()
