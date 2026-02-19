import asyncio
from jira_client import JiraClient

async def main():
    print("Testing Jira Get Attachment Content...")
    j = JiraClient()

    # Test with known attachments from RET-639
    test_cases = [
        ("200831", "WEBHOOK_INSTRUCTIONS.md"),  # text file
        ("198856", "image-20260120-155830.png"),  # image file
    ]

    for attachment_id, expected_name in test_cases:
        print(f"\n  Downloading {expected_name} (ID: {attachment_id})...")
        try:
            result = await j.get_attachment_content(attachment_id)
            if result:
                print(f"  SUCCESS: {result['filename']} ({result['mimeType']}, {len(result['data'])} bytes)")
                print(f"  First 20 bytes: {result['data'][:20]}")
            else:
                print("  Failed: returned None.")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
