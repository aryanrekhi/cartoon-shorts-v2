# Cartoon Shorts v2 — The Overhaul

Fully automated YouTube video factory. Generates scripts, images, voiceover, captions, background audio — assembles finished videos and uploads them to YouTube. Runs on GitHub Actions for free. You don't touch your laptop.

## What changed from v1 (and why)

### Problem 1: "Stories don't make sense"
**Old:** Generic prompt → "write about unsolved mysteries" → vague, repetitive slop.
**New:** Structured story engine with 5-beat narrative arcs. Forces the LLM to use specific names, dates, places. Each topic in `topics.txt` is a SPECIFIC story, not a vague category.

### Problem 2: "Visuals are very bad"
**Old:** 30-word prompts to Pollinations/Flux → 2020-era quality.
**New:** 50-80 word cinematic prompts with mood-aware lighting, camera angles, and atmosphere. Tries multiple image models. Scene-by-scene visual direction baked into the script.

### Problem 3: "Just says the same thing in different paraphrasing"
**Old:** No story structure → LLM repeats itself.
**New:** 5-beat narrative templates (Hook → Setup → Escalation → Twist → Cliffhanger). Each beat has a specific job. The LLM can't repeat because each beat demands different content.

### Problem 4: No production polish
**Old:** No music, basic captions, no atmosphere.
**New:** Ambient background audio matched to mood, mood-aware Ken Burns motion, styled captions with pop animation.

### Bonus: Long-form support
**New:** Can generate 8-15 minute documentary-style videos (16:9 horizontal) in addition to shorts.

## What's free (everything)

| Component | Tool | Cost |
|-----------|------|------|
| Scripts | Gemini / Groq / Cerebras / Pollinations (failover chain) | Free |
| Images | Pollinations.ai (Flux models) | Free, unlimited |
| Voice | Microsoft Edge TTS | Free, unlimited |
| Captions | OpenAI Whisper (runs on GitHub's CPU) | Free |
| Music | Generated ambient audio (numpy) | Free |
| Video assembly | moviepy + ffmpeg | Free |
| Upload | YouTube Data API | Free (6 uploads/day) |
| Cloud compute | GitHub Actions (public repo) | Free, unlimited |

## Quick start (local test)

```bash
# Install
pip install -r requirements.txt

# Build one video
python make_video.py --topic "The Dyatlov Pass incident" --name test_01 --style cinematic

# Check output/test_01.mp4
```

## Cloud setup (run forever, free)

### 1. Get free API keys (optional but recommended)

These are all free and dramatically improve script quality:

- **Gemini:** https://aistudio.google.com/app/apikey → free tier
- **Groq:** https://console.groq.com → free tier
- **Cerebras:** https://cloud.cerebras.ai → free tier

Without any keys, it falls back to Pollinations text API (slower but works).

### 2. Create GitHub repo

1. Create account at github.com (free)
2. New repository → name it anything → **Public** (required for free Actions)
3. Upload all these files

### 3. Add secrets

Repo → Settings → Secrets and variables → Actions → New repository secret:

- `GEMINI_API_KEY` — your Gemini key
- `GROQ_API_KEY` — your Groq key (optional)
- `CEREBRAS_API_KEY` — your Cerebras key (optional)

For YouTube upload (do this after you're happy with quality):
- `YOUTUBE_CLIENT_SECRET` — from setup_cloud_credentials.py
- `YOUTUBE_TOKEN` — from setup_cloud_credentials.py

### 4. Test

Actions tab → "Daily Video Factory" → Run workflow → count=2, upload=false

Watch it run. Check the video artifacts when done.

### 5. Go live

Once quality is good, enable the daily schedule. Edit `.github/workflows/daily.yml`:
- The `cron: '30 21 * * *'` line controls timing (21:30 UTC = 3:00 AM IST)
- Set upload to true in the scheduled run

## Customizing

### Topics
Edit `topics.txt`. Each line is a SPECIFIC story topic with enough detail for the AI to research.

Bad: `unsolved mysteries`
Good: `The Hinterkaifeck murders — six people killed on a German farm in 1922, and the killer lived with the bodies for days`

### Visual styles
`cinematic` `anime` `noir` `comic` `realistic` `fantasy` `retro`

### Voices
`narrator` `dramatic` `warm` `female` `british` `energetic` `deep`

### Long-form videos
```bash
python autopilot.py --long --topic "The history of the Bermuda Triangle"
```
Generates one 8-minute horizontal (16:9) documentary.

## File structure

```
├── autopilot.py           # Daily automation controller
├── make_video.py          # Core: builds one video end-to-end
├── story_engine.py        # Script generation with narrative structure
├── llm_client.py          # Multi-provider LLM client
├── upload.py              # YouTube uploader
├── topics.txt             # Topic rotation list
├── requirements.txt
├── .github/workflows/
│   └── daily.yml          # GitHub Actions schedule
├── output/                # Finished videos appear here
└── temp/                  # Working files (safe to delete)
```

## Realistic expectations

- **Shorts:** ~8 min per video on GitHub Actions
- **Long-form:** ~25 min per video on GitHub Actions
- **Quality:** Significantly better than v1, but still AI-generated. Good enough for storytelling/mystery/explainer niches. Not Pixar.
- **Monetization:** 6-12 months of consistent daily uploads. YouTube requires 1,000 subs + 4,000 watch hours OR 10M Shorts views.
- **Risk:** YouTube demonetizes pure AI-slop channels. These scripts have real research and structure, which helps. But always review your content.
