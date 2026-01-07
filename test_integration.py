import asyncio
from jira_client import JiraClient
from confluence_client import ConfluenceClient

async def main():
    print("Testing Jira Integration...")
    try:
        jira = JiraClient()
        print("  Listing issues...")
        issues = await jira.list_issues(max_results=5)
        print(f"  Found {len(issues)} issues.")
        if issues:
            key = issues[0]["key"]
            print(f"  Reading issue {key}...")
            issue = await jira.get_issue(key)
            print(f"  Issue summary: {issue['fields']['summary']}")
    except Exception as e:
        print(f"  Jira Error: {e}")

    print("\nTesting Confluence Integration...")
    try:
        confluence = ConfluenceClient()
        print("  Listing pages...")
        pages = await confluence.list_pages(limit=5)
        print(f"  Found {len(pages)} pages.")
        if pages:
            page_id = pages[0]["id"]
            title = pages[0]["title"]
            print(f"  Reading page {page_id} ('{title}')...")
            page = await confluence.get_page(page_id)
            print(f"  Page version: {page['version']}")
    except Exception as e:
        print(f"  Confluence Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
