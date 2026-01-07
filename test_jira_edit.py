import asyncio
import os
from jira_client import JiraClient

# WARNING: This test modifies data. Use with caution or on a test issue.
# Ensure you have a test issue key, e.g., TEST-1, or SCRUM-83 as seen in logs.
TEST_ISSUE_KEY = "SCRUM-83"

async def main():
    print("Testing Jira Edit Tools...")
    try:
        jira = JiraClient()
        
        # 1. Add Comment
        print(f"  Adding comment to {TEST_ISSUE_KEY}...")
        comment = await jira.add_comment(TEST_ISSUE_KEY, "Test comment from MCP integration test.")
        print(f"  Comment added: {comment['id']}")
        
        # 2. Update Issue (Summary) - Append timestamp to avoid idempotent issues?
        # Or just toggle specific suffix.
        print(f"  Updating issue {TEST_ISSUE_KEY} summary...")
        # Get current summary first
        issue = await jira.get_issue(TEST_ISSUE_KEY)
        original_summary = issue["fields"]["summary"]
        new_summary = f"{original_summary} (Updated)"
        # If already updated, strip it?
        if "(Updated)" in original_summary:
             new_summary = original_summary.replace(" (Updated)", "")
             
        await jira.update_issue(TEST_ISSUE_KEY, {"summary": new_summary})
        print(f"  Issue updated. New summary: '{new_summary}'")
        
        # 3. Get Transitions
        print(f"  Getting transitions for {TEST_ISSUE_KEY}...")
        transitions = await jira.get_transitions(TEST_ISSUE_KEY)
        print(f"  Found {len(transitions)} transitions:")
        for t in transitions:
            print(f"    - ID: {t['id']}, Name: {t['name']}, To: {t['to']['name']}")
            
        # 4. Transition Issue (Dry run / Interactive?)
        # Transitioning moves state, which might be annoying.
        # I'll just print that we CAN transition if IDs exist.
        if transitions:
            print("  Skipping actual transition to avoid changing workflow state unexpectedly.")
            # await jira.transition_issue(TEST_ISSUE_KEY, transitions[0]['id'])
            
    except Exception as e:
        print(f"  Jira Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
