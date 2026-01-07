import os
import httpx
import base64
import logging
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("atlassian-mcp.confluence")

class ConfluenceClient:
    def __init__(self):
        self.base_url = os.getenv("CONFLUENCE_URL")
        self.username = os.getenv("ATLASSIAN_USERNAME")
        self.api_key = os.getenv("ATLASSIAN_API_KEY")
        self.default_space = os.getenv("CONFLUENCE_SPACE_KEY")
        
        if not all([self.base_url, self.username, self.api_key]):
            raise ValueError("Missing Confluence configuration in .env")
            
        auth_str = f"{self.username}:{self.api_key}"
        self.auth_header = {
            "Authorization": f"Basic {base64.b64encode(auth_str.encode()).decode()}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Confluence API v2 uses a different base for some endpoints, but let's stick to the URL provided
        # The provided URL is `.../wiki`. The REST API is usually at `.../wiki/rest/api` or `.../wiki/api/v2`
        # I'll check if the provided URL includes `/rest/api`.
        # The configuration shows: CONFLUENCE_URL=https://caelibenefits-team.atlassian.net/wiki
        # So I will append `/rest/api` to it.
        
        if not self.base_url.endswith("/rest/api"):
             self.api_base = f"{self.base_url}/rest/api"
        else:
             self.api_base = self.base_url

    async def list_pages(self, space_key: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        space = space_key or self.default_space
        if not space:
            raise ValueError("No space key provided and no default configured")
            
        # Using content search
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/content",
                params={
                    "spaceKey": space,
                    "type": "page",
                    "limit": limit,
                    "expand": "version"
                },
                headers=self.auth_header
            )
            response.raise_for_status()
            data = response.json()
            return [
                {
                    "id": page["id"],
                    "title": page["title"],
                    "version": page["version"]["number"],
                    "link": page["_links"]["webui"]
                }
                for page in data.get("results", [])
            ]

    async def get_page(self, page_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/content/{page_id}",
                params={"expand": "body.storage,version"},
                headers=self.auth_header
            )
            response.raise_for_status()
            data = response.json()
            return {
                "id": data["id"],
                "title": data["title"],
                "version": data["version"]["number"],
                "body": data["body"]["storage"]["value"]
            }

    async def update_page(self, page_id: str, title: str, content: str, version: Optional[int] = None) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            # If version is not provided, fetch the current version first
            if version is None:
                current_page = await self.get_page(page_id)
                current_version = current_page["version"]
                version = current_version + 1
            
            payload = {
                "id": page_id,
                "type": "page",
                "title": title,
                "body": {
                    "storage": {
                        "value": content,
                        "representation": "storage"
                    }
                },
                "version": {
                    "number": version
                }
            }
            response = await client.put(
                f"{self.api_base}/content/{page_id}",
                json=payload,
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json()
    async def create_page(self, title: str, content: str, parent_id: Optional[str] = None, space_key: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new page in Confluence."""
        space = space_key or self.default_space
        if not space:
            raise ValueError("No space key provided and no default configured")

        async with httpx.AsyncClient() as client:
            payload = {
                "title": title,
                "type": "page",
                "space": {"key": space},
                "body": {
                    "storage": {
                        "value": content,
                        "representation": "storage"
                    }
                }
            }
            if parent_id:
                payload["ancestors"] = [{"id": parent_id}]

            response = await client.post(
                f"{self.api_base}/content",
                json=payload,
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json()

    async def delete_page(self, page_id: str) -> None:
        """Deletes a page in Confluence."""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.api_base}/content/{page_id}",
                headers=self.auth_header
            )
            response.raise_for_status()

    async def search(self, cql: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Searches Confluence using CQL."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/content/search",
                params={
                    "cql": cql,
                    "limit": limit,
                    "expand": "version"
                },
                headers=self.auth_header
            )
            response.raise_for_status()
            data = response.json()
            return [
                {
                    "id": page["id"],
                    "title": page["title"],
                    "version": page["version"]["number"],
                    "link": page["_links"]["webui"]
                }
                for page in data.get("results", [])
            ]

    async def get_comments(self, page_id: str) -> List[Dict[str, Any]]:
        """Gets all comments for a Confluence page."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/content/{page_id}/child/comment",
                params={"expand": "body.storage,version"},
                headers=self.auth_header
            )
            response.raise_for_status()
            data = response.json()
            return [
                {
                    "id": comment.get("id"),
                    "author": (comment.get("version") or {}).get("by", {}).get("displayName", "Unknown"),
                    "created": (comment.get("version") or {}).get("when"),
                    "body": (comment.get("body") or {}).get("storage", {}).get("value", "")
                }
                for comment in data.get("results", [])
            ]

    async def add_comment(self, page_id: str, body: str, parent_comment_id: Optional[str] = None) -> Dict[str, Any]:
        """Adds a comment to a Confluence page. Optionally replies to an existing comment."""
        async with httpx.AsyncClient() as client:
            payload = {
                "type": "comment",
                "container": {
                    "type": "page",
                    "id": page_id
                },
                "body": {
                    "storage": {
                        "value": f"<p>{body}</p>",
                        "representation": "storage"
                    }
                }
            }
            # If replying to a comment, set the ancestor
            if parent_comment_id:
                payload["ancestors"] = [{"id": parent_comment_id}]
            
            response = await client.post(
                f"{self.api_base}/content",
                json=payload,
                headers=self.auth_header
            )
            response.raise_for_status()
            return response.json()
