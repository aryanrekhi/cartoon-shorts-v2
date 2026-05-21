"""
AUTOPILOT v2 — Full daily pipeline on steroids.
=================================================
One command. Picks topic, generates scripts, builds videos, uploads.
Schedule via GitHub Actions (free cloud) or cron.

USAGE:
    python autopilot.py                         # build only (review first!)
    python autopilot.py --upload                # build + upload
    python autopilot.py --count 3               # 3 videos today
    python autopilot.py --style noir            # noir style today
    python autopilot.py --topic "Dyatlov Pass"  # override topic
    python autopilot.py --long                  # one long-form video instead
"""

import argparse
import asyncio
import datetime
import json
import logging
import subprocess
import sys
from pathlib import Path

from make_video import build_video, VISUAL_STYLES, VOICES, FORMATS
from story_engine import generate_script, generate_long_script


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        handlers=[
            logging.FileHandler("autopilot.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("autopilot")


def get_todays_topic(topics_file="topics.txt", override=""):
    if override:
        return override
    p = Path(topics_file)
    if not p.exists():
        return "The Dyatlov Pass incident — nine hikers found dead in the Ural Mountains"
    topics = [
        l.strip() for l in p.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]
    if not topics:
        return "unexplained historical mysteries"
    day = datetime.date.today().toordinal()
    return topics[day % len(topics)]


def get_todays_style(override=""):
    if override:
        return override
    styles = list(VISUAL_STYLES.keys())
    day = datetime.date.today().toordinal()
    # Rotate through styles weekly
    return styles[day % len(styles)]


async def run(args, log):
    topic = get_todays_topic(override=args.topic)
    style = get_todays_style(override=args.style)
    today = datetime.date.today().isoformat()

    log.info(f"{'='*60}")
    log.info(f"  AUTOPILOT v2 — {today}")
    log.info(f"  Topic: {topic}")
    log.info(f"  Style: {style} | Voice: {args.voice} | Count: {args.count}")
    log.info(f"{'='*60}")

    output_dir = Path("output")
    temp_dir = Path("temp")

    built = []

    if args.long:
        # ── Long-form mode: one 8-min video ──
        log.info("MODE: Long-form (8 minutes)")
        slug = f"{today}_long"
        out = output_dir / f"{slug}.mp4"
        if out.exists() and not args.overwrite:
            log.info(f"  {slug}.mp4 exists, skipping")
            built.append(out)
        else:
            try:
                log.info(f"  Generating long script...")
                script_data = generate_long_script(topic, duration_minutes=8)
                if script_data:
                    result = await build_video(
                        topic=topic, name=slug, style=style, voice=args.voice,
                        video_format="long", output_dir=output_dir, temp_dir=temp_dir,
                        duration_seconds=480, script_data=script_data,
                    )
                    if result:
                        built.append(result)
                else:
                    log.error("  Long script generation failed")
            except Exception as e:
                log.exception(f"  Failed: {e}")
    else:
        # ── Shorts mode: multiple short videos ──
        log.info(f"MODE: Shorts ({args.count} videos)")
        for i in range(args.count):
            slug = f"{today}_{i+1:02d}"
            out = output_dir / f"{slug}.mp4"
            if out.exists() and not args.overwrite:
                log.info(f"  {slug}.mp4 exists, skipping")
                built.append(out)
                continue

            log.info(f"\n  [{i+1}/{args.count}] Building {slug}...")
            try:
                # Vary the topic slightly for each video
                varied_topic = topic
                if args.count > 1 and i > 0:
                    varied_topic = f"{topic} — a different angle, video {i+1}"

                result = await build_video(
                    topic=varied_topic, name=slug, style=style, voice=args.voice,
                    video_format="short", output_dir=output_dir, temp_dir=temp_dir,
                    duration_seconds=args.length,
                )
                if result:
                    built.append(result)
            except Exception as e:
                log.exception(f"  ❌ {slug} failed: {e}")

    log.info(f"\n  Built {len(built)} videos")

    # ── Upload ──
    if args.upload and built:
        log.info("📤  Uploading...")
        try:
            subprocess.run(
                [sys.executable, "upload.py", "--batch",
                 "--schedule", args.schedule, "--move-uploaded"],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            log.error(f"Upload failed: {e}")
    elif built:
        log.info("Skipping upload (use --upload to enable)")

    log.info(f"{'='*60}")
    log.info("  AUTOPILOT DONE")
    log.info(f"{'='*60}\n")


def main():
    p = argparse.ArgumentParser(description="Autopilot v2")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--length", type=int, default=50, help="Target seconds per short")
    p.add_argument("--style", default="", help="Override style (default: auto-rotate)")
    p.add_argument("--voice", default="narrator", choices=list(VOICES))
    p.add_argument("--topic", default="")
    p.add_argument("--upload", action="store_true")
    p.add_argument("--schedule", default="3hours")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--long", action="store_true", help="Build one long-form video instead")
    args = p.parse_args()

    log = setup_logging()
    try:
        asyncio.run(run(args, log))
    except KeyboardInterrupt:
        log.warning("Interrupted")
    except Exception:
        log.exception("Crashed")


if __name__ == "__main__":
    main()
