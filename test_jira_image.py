import asyncio
from jira_client import JiraClient
import httpx

async def main():
    print("Testing Jira Get Attachment Image...")
    j = JiraClient()
    
    issue_key = "SCRUM-81"
    
    # helper to find an attachment filename first
    filename = None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{j.base_url}/issue/{issue_key}",
                params={"fields": "attachment"},
                headers=j.auth_header
            )
            data = response.json()
            attachments = (data.get("fields") or {}).get("attachment", [])
            if attachments:
                attachment = attachments[0]
                attachment_id = attachment["id"]
                filename = attachment["filename"]
                print(f"  Found attachment: {filename} (ID: {attachment_id})")
            else:
                print("  No attachments found on SCRUM-81. Cannot test download.")
                return

        if attachment_id:
            print(f"  Downloading attachment {attachment_id}...")
            image_data = await j.download_attachment(attachment_id)
            
            if image_data:
                print(f"  SUCCESS: Downloaded {len(image_data)} bytes.")
                # Verify it looks like a file (check first few bytes)
                print(f"  First 10 bytes: {image_data[:10]}")
            else:
                print("  Failed to download image data (returned None).")

    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
