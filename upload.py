"""
YouTube Auto-Uploader
=====================
Uploads finished .mp4 files from output/ folder to your YouTube channel.

SETUP (one-time, ~10 minutes):
1. Go to https://console.cloud.google.com/
2. Create a new project
3. Enable "YouTube Data API v3"
4. Create OAuth 2.0 credentials (Desktop application)
5. Download credentials JSON → save as `client_secret.json` next to this file
6. Run this script once — it'll open a browser to authorize. After that, it stores
   a token and runs unattended.

USAGE:
    python upload.py --file output/my_video.mp4 --title "Mystery!" --tags "shorts,mystery,truecrime"
    python upload.py --batch                        # upload everything in output/
    python upload.py --batch --schedule 2hours      # space uploads 2 hours apart

Daily 5-7 uploads: combine batch_generate.py with this on a cron schedule.
"""

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
except ImportError:
    print("Install: pip install google-auth-oauthlib google-api-python-client")
    raise

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"


def get_youtube_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET_FILE):
                raise FileNotFoundError(
                    f"Place your OAuth credentials at ./{CLIENT_SECRET_FILE} "
                    "(see setup instructions in upload.py)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_video(
    file_path: Path,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "24",  # 24 = Entertainment
    privacy_status: str = "public",
    publish_at: datetime = None,
):
    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title[:100],  # YouTube 100-char limit
            "description": description[:5000],
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": "private" if publish_at else privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    if publish_at:
        body["status"]["publishAt"] = publish_at.astimezone(timezone.utc).isoformat()

    media = MediaFileUpload(str(file_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    print(f"📤  Uploading {file_path.name} ...")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"   {int(status.progress() * 100)}%")
        except HttpError as e:
            print(f"   ❌ {e}")
            return None

    vid_id = response.get("id")
    print(f"✅  Uploaded: https://youtu.be/{vid_id}")
    return vid_id


def upload_one(args):
    sidecar = args.file.replace(".mp4", ".json")
    title = args.title
    description = args.description
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if os.path.exists(sidecar):
        meta = json.loads(Path(sidecar).read_text())
        title = title or meta.get("title")
        description = description or meta.get("description", "")
        tags = tags or meta.get("tags", [])

    if not title:
        title = Path(args.file).stem.replace("_", " ").title()
    if not description:
        description = f"{title}\n\n#Shorts #shorts"

    upload_video(
        file_path=Path(args.file),
        title=title,
        description=description,
        tags=tags or ["shorts"],
        privacy_status=args.privacy,
    )


def upload_batch(args):
    folder = Path(args.output_dir)
    videos = sorted(folder.glob("*.mp4"))
    if not videos:
        print(f"No .mp4 files in {folder}")
        return

    schedule_hours = parse_schedule(args.schedule) if args.schedule else 0
    base_time = datetime.now(timezone.utc) + timedelta(hours=1)

    for i, video in enumerate(videos):
        sidecar = video.with_suffix(".json")
        if sidecar.exists():
            meta = json.loads(sidecar.read_text())
            title = meta.get("title", video.stem.replace("_", " ").title())
            description = meta.get("description", f"{title}\n\n#Shorts")
            tags = meta.get("tags", ["shorts"])
        else:
            title = video.stem.replace("_", " ").title()
            description = f"{title}\n\n#Shorts #shorts"
            tags = ["shorts"]

        publish_at = base_time + timedelta(hours=schedule_hours * i) if schedule_hours else None

        try:
            vid_id = upload_video(
                file_path=video,
                title=title,
                description=description,
                tags=tags,
                privacy_status=args.privacy,
                publish_at=publish_at,
            )
            if vid_id and args.move_uploaded:
                done = folder / "uploaded"
                done.mkdir(exist_ok=True)
                video.rename(done / video.name)
        except Exception as e:
            print(f"   ❌ failed for {video.name}: {e}")
            continue
        time.sleep(2)


def parse_schedule(s: str) -> float:
    s = s.lower().strip()
    if s.endswith("hours") or s.endswith("hour") or s.endswith("h"):
        return float(s.rstrip("hoursurs"))
    if s.endswith("min") or s.endswith("minutes") or s.endswith("m"):
        return float(s.rstrip("minutes")) / 60
    return float(s)


def main():
    p = argparse.ArgumentParser(description="YouTube auto-uploader")
    p.add_argument("--file", help="Single .mp4 to upload")
    p.add_argument("--title", default="")
    p.add_argument("--description", default="")
    p.add_argument("--tags", default="shorts")
    p.add_argument("--privacy", default="public", choices=["public", "private", "unlisted"])
    p.add_argument("--batch", action="store_true", help="Upload all videos in output/")
    p.add_argument("--output-dir", default="output")
    p.add_argument("--schedule", default="", help="Space uploads, e.g. '2hours'")
    p.add_argument("--move-uploaded", action="store_true", help="Move uploaded files to output/uploaded/")
    args = p.parse_args()

    if args.batch:
        upload_batch(args)
    elif args.file:
        upload_one(args)
    else:
        p.error("Pass --file or --batch")


if __name__ == "__main__":
    main()
