import asyncio
from confluence_client import ConfluenceClient

async def main():
    print("Testing Confluence Auto-Version Update...")
    c = ConfluenceClient()
    page_id = "167608321" # Known dev page
    
    try:
        # 1. Get current state
        print(f"  Fetching page {page_id}...")
        page = await c.get_page(page_id)
        print(f"  Current Version: {page['version']}")
        original_title = page['title']
        original_body = page['body']
        
        # 2. Update without version (should auto-increment)
        print(f"  Updating page {page_id} (no version provided)...")
        # specific change to force update
        new_body = original_body + "\n<p><em>Auto-version update test</em></p>"
        
        result = await c.update_page(page_id, original_title, new_body, version=None)
        
        new_version = result['version']['number']
        print(f"  Update Successful!")
        print(f"  New Version: {new_version}")
        
        if new_version == page['version'] + 1:
            print("  SUCCESS: Version auto-incremented correctly.")
        else:
            print(f"  WARNING: Expected version {page['version'] + 1}, got {new_version}")

        # 3. Clean up (Revert) - optional but polite
        # print("  Reverting change...")
        # await c.update_page(page_id, original_title, original_body, version=None)
        # print("  Reverted.")

    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
