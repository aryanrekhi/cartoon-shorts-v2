"""
ONE-TIME local setup for cloud-based YouTube uploads.
=====================================================
Run this ONCE on your laptop. It handles the Google OAuth dance (which needs
a browser), then dumps the resulting tokens into a file you can paste into
GitHub Secrets. After that, your laptop never has to be involved again — the
cloud picks up from here.

USAGE:
    python setup_cloud_credentials.py

PREREQUISITE:
    You need client_secret.json in this folder. To get it:
      1. Go to https://console.cloud.google.com/
      2. Create a project (any name)
      3. Search bar → "YouTube Data API v3" → Enable
      4. APIs & Services → OAuth consent screen:
           - User type: External
           - App name: whatever you want
           - User support email: your email
           - Developer contact: your email
           - Save and continue (skip scopes & test users for now)
           - On "Test users" page → ADD YOUR OWN GOOGLE ACCOUNT EMAIL → save
      5. APIs & Services → Credentials → Create Credentials → OAuth client ID
           - Application type: Desktop app
           - Name: anything
           - Create
      6. Download JSON → rename to client_secret.json → put it next to this script
"""

import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("First install the YouTube deps:")
    print("    pip install google-auth-oauthlib google-api-python-client")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"
OUTPUT_FILE = "CLOUD_SECRETS_PASTE_INTO_GITHUB.txt"


def main():
    print("\n" + "=" * 64)
    print("  CLOUD CREDENTIALS SETUP — runs once, never again")
    print("=" * 64 + "\n")

    if not Path(CLIENT_SECRET_FILE).exists():
        print(f"❌  Missing {CLIENT_SECRET_FILE} in this folder.")
        print(f"\nRead the comment at the top of {Path(__file__).name} for how to get it.")
        print("(Takes ~10 minutes; one-time only.)\n")
        return

    print("✓  Found client_secret.json")
    print("\nOpening browser for Google login + permission grant...")
    print("(If the browser doesn't open, copy the URL it prints to your phone.)\n")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    Path(TOKEN_FILE).write_text(creds.to_json(), encoding="utf-8")

    print("\n✓  Auth complete. Tokens saved locally.\n")

    client_secret_content = Path(CLIENT_SECRET_FILE).read_text(encoding="utf-8").strip()
    token_content = Path(TOKEN_FILE).read_text(encoding="utf-8").strip()

    bar = "─" * 63
    out = (
        "╔" + "═" * 63 + "╗\n"
        "║  COPY THESE INTO GITHUB SECRETS                              ║\n"
        "║  (Your repo → Settings → Secrets and variables → Actions)    ║\n"
        "╚" + "═" * 63 + "╝\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  SECRET #1\n"
        "  Name:   YOUTUBE_CLIENT_SECRET\n"
        "  Value:  (copy the JSON between the lines)\n"
        f"{bar}\n"
        f"{client_secret_content}\n"
        f"{bar}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  SECRET #2\n"
        "  Name:   YOUTUBE_TOKEN\n"
        "  Value:  (copy the JSON between the lines)\n"
        f"{bar}\n"
        f"{token_content}\n"
        f"{bar}\n\n"
        "════════════════════════════════════════════════════════════════\n"
        " ⚠  DELETE THIS FILE AFTER COPYING. It contains live credentials.\n"
        "════════════════════════════════════════════════════════════════\n"
    )

    Path(OUTPUT_FILE).write_text(out, encoding="utf-8")
    print(f"📄  Wrote {OUTPUT_FILE}\n")
    print("Next steps:")
    print(f"  1. Open {OUTPUT_FILE} in Notepad")
    print( "  2. Follow the instructions inside to paste into GitHub")
    print( "  3. Delete the file after you're done")
    print( "  4. See GITHUB_CLOUD_SETUP.md for the full walkthrough\n")


if __name__ == "__main__":
    main()
