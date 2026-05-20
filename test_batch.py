# test_all_emails.py
from tools.mail_fetcher_tool import MailFetcherTool
import requests

fetcher = MailFetcherTool()

# Get ALL recent emails (read AND unread)
url = "https://graph.microsoft.com/v1.0/me/messages"
params = {
    "$top": 10,
    "$select": "id,subject,from,hasAttachments,isRead,receivedDateTime",
    "$orderby": "receivedDateTime desc"
}

r = requests.get(url, headers=fetcher._headers(), params=params, timeout=30)
print(f"Status: {r.status_code}")
messages = r.json().get("value", [])

print(f"\n{'='*60}")
print(f"ALL RECENT EMAILS: {len(messages)}")
print(f"{'='*60}")

for i, msg in enumerate(messages, 1):
    print(f"\n{i}. {'📬 UNREAD' if not msg.get('isRead') else '📖 READ'}")
    print(f"   Subject: {msg.get('subject', '')[:80]}")
    print(f"   Has Attachment: {msg.get('hasAttachments')}")
    print(f"   Date: {msg.get('receivedDateTime', '')[:19]}")