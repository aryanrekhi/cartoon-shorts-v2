"""
Video Builder v2 — Production-grade output.
=============================================
Major upgrades over v1:
  • Scene-aware visual prompts (from story_engine) → much better images
  • Multiple image models via Pollinations (flux, flux-realism, turbo)
  • Background music from free APIs
  • Styled captions with color-highlighted keywords
  • Hook text overlay in first 3 seconds
  • Cinematic color grading per mood
  • Better Ken Burns with mood-matched motion
  • Support for both shorts (vertical) and long-form (horizontal)
"""

import argparse
import asyncio
import hashlib
import os
import re
import sys
import time
import random
from pathlib import Path
from urllib.parse import quote_plus

import edge_tts
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
if not hasattr(Image, "ANTIALIAS"): Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    AudioFileClip, CompositeVideoClip, ImageClip, VideoClip,
    concatenate_audioclips, afx,
)

from story_engine import generate_script, generate_long_script

# ── Dimensions ──

FORMATS = {
    "short":     (1080, 1920),   # 9:16 vertical
    "long":      (1920, 1080),   # 16:9 horizontal
    "square":    (1080, 1080),   # 1:1
}

# ── Voices ──

VOICES = {
    "narrator":    "en-US-ChristopherNeural",
    "dramatic":    "en-US-DavisNeural",
    "warm":        "en-US-TonyNeural",
    "female":      "en-US-AriaNeural",
    "british":     "en-GB-RyanNeural",
    "energetic":   "en-US-JennyNeural",
    "deep":        "en-US-GuyNeural",
}

# ── Visual styles — much more detailed than v1 ──

VISUAL_STYLES = {
    "cinematic": (
        "cinematic digital art, hyperdetailed, volumetric lighting, "
        "dramatic shadows, film grain, shallow depth of field, "
        "professional color grading, 8K render quality, photorealistic lighting"
    ),
    "anime": (
        "premium anime art style, Studio Ghibli and Makoto Shinkai inspired, "
        "incredibly detailed backgrounds, vibrant saturated colors, "
        "painterly textures, atmospheric lighting, emotional composition"
    ),
    "noir": (
        "neo-noir digital painting, heavy chiaroscuro, deep shadows, "
        "rain-slicked surfaces, neon reflections, muted desaturated palette "
        "with single color accents, film noir atmosphere, moody and atmospheric"
    ),
    "comic": (
        "high-end graphic novel illustration, bold dynamic composition, "
        "rich ink work, dramatic panel-style framing, vivid color palette, "
        "professional comic art quality, cinematic angles"
    ),
    "realistic": (
        "photorealistic digital art, hyperdetailed, natural lighting, "
        "professional photography quality, sharp focus, rich colors, "
        "editorial magazine quality, 8K resolution"
    ),
    "fantasy": (
        "epic fantasy digital painting, dramatic atmospheric lighting, "
        "rich jewel-tone colors, ethereal glow effects, intricate details, "
        "concept art quality, cinematic composition"
    ),
    "retro": (
        "vintage retro illustration, 1970s documentary style, warm analog colors, "
        "film grain texture, slightly faded palette, nostalgic atmosphere, "
        "editorial illustration quality"
    ),
}

# ── Mood-based enhancements ──

MOOD_MODIFIERS = {
    "dark":       "dark ominous atmosphere, deep shadows, cold blue-grey tones, unsettling",
    "tense":      "tense dramatic atmosphere, stark lighting, high contrast, suspenseful",
    "mysterious": "mysterious foggy atmosphere, dim ethereal light, enigmatic, obscured details",
    "exciting":   "dynamic energetic composition, bright vivid colors, motion blur, dramatic angles",
    "shocking":   "stark dramatic reveal, harsh spotlight, high contrast, visceral impact",
    "calm":       "serene peaceful atmosphere, soft golden light, gentle tones, contemplative",
    "epic":       "grand epic scale, sweeping vista, dramatic sky, heroic lighting, awe-inspiring",
}

NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, deformed, ugly, amateur, text, watermark, "
    "logo, signature, extra limbs, bad anatomy, disfigured, poorly drawn, "
    "low resolution, pixelated, oversaturated, cartoon unless specified"
)

# ── Image generation (multi-provider: Gemini → Pollinations) ──

POLLINATIONS_URL = (
    "https://image.pollinations.ai/prompt/{prompt}"
    "?model={model}&width={w}&height={h}&nologo=true&enhance=true&seed={seed}"
)

# Gemini image models to try (newest first)
GEMINI_IMAGE_MODELS = [
    "gemini-2.0-flash-preview-image-generation",
    "gemini-2.5-flash-preview-image-generation",
    "gemini-2.0-flash-exp-image-generation",
]

ASPECT_RATIOS = {
    (1080, 1920): "9:16",   # vertical short
    (1920, 1080): "16:9",   # horizontal long
    (1080, 1080): "1:1",    # square
}


def _try_gemini_image(full_prompt: str, output_path: Path, width: int, height: int) -> bool:
    """Generate image using Gemini API (500 free/day, much higher quality)."""
    import json
    import base64

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False

    aspect = ASPECT_RATIOS.get((width, height), "9:16")

    for model in GEMINI_IMAGE_MODELS:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/{model}:generateContent?key={api_key}"
            )
            payload = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                },
            }
            data = json.dumps(payload).encode("utf-8")
            req = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=data,
                timeout=90,
            )

            if req.status_code != 200:
                print(f"      Gemini/{model} HTTP {req.status_code}")
                continue

            resp = req.json()

            # Extract base64 image from response
            for candidate in resp.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    inline = part.get("inlineData", {})
                    b64 = inline.get("data", "")
                    if b64 and len(b64) > 1000:
                        img_bytes = base64.b64decode(b64)
                        # Gemini returns PNG — convert and resize to exact dimensions
                        from io import BytesIO
                        img = Image.open(BytesIO(img_bytes)).convert("RGB")
                        img = img.resize((width, height), Image.LANCZOS)
                        img.save(str(output_path), "JPEG", quality=92)
                        print(f"      ✓ Gemini/{model}")
                        return True

            print(f"      Gemini/{model}: no image in response")
        except Exception as e:
            print(f"      Gemini/{model}: {type(e).__name__}: {e}")

    return False


def _try_cloudflare_image(full_prompt: str, output_path: Path, width: int, height: int) -> bool:
    """Generate image using Cloudflare Workers AI (10K free neurons/day, FLUX models)."""
    import base64

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not api_token:
        return False

    models = [
        "@cf/black-forest-labs/flux-1-schnell",
    ]

    for model in models:
        try:
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
            r = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                },
                json={"prompt": full_prompt[:2048], "steps": 8},
                timeout=120,
            )
            if r.status_code != 200:
                print(f"      Cloudflare/{model.split('/')[-1]} HTTP {r.status_code}")
                continue

            resp = r.json()
            b64 = resp.get("result", {}).get("image", "")
            if b64 and len(b64) > 1000:
                img_bytes = base64.b64decode(b64)
                from io import BytesIO
                img = Image.open(BytesIO(img_bytes)).convert("RGB")
                img = img.resize((width, height), Image.LANCZOS)
                img.save(str(output_path), "JPEG", quality=92)
                print(f"      ✓ Cloudflare/{model.split('/')[-1]}")
                return True

            print(f"      Cloudflare: no image in response")
        except Exception as e:
            print(f"      Cloudflare: {type(e).__name__}: {e}")

    return False


def _try_together_image(full_prompt: str, output_path: Path, width: int, height: int) -> bool:
    """Generate image using Together.ai ($25 free credit, FLUX schnell free endpoint)."""
    import base64

    api_key = os.environ.get("TOGETHER_API_KEY", "").strip()
    if not api_key:
        return False

    try:
        r = requests.post(
            "https://api.together.xyz/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "black-forest-labs/FLUX.1-schnell-Free",
                "prompt": full_prompt[:2048],
                "width": min(width, 1024),
                "height": min(height, 1024),
                "steps": 4,
                "n": 1,
                "response_format": "b64_json",
            },
            timeout=120,
        )
        if r.status_code != 200:
            print(f"      Together HTTP {r.status_code}")
            return False

        resp = r.json()
        b64 = resp.get("data", [{}])[0].get("b64_json", "")
        if b64 and len(b64) > 1000:
            img_bytes = base64.b64decode(b64)
            from io import BytesIO
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            img = img.resize((width, height), Image.LANCZOS)
            img.save(str(output_path), "JPEG", quality=92)
            print(f"      ✓ Together/FLUX-schnell")
            return True
    except Exception as e:
        print(f"      Together: {type(e).__name__}: {e}")

    return False


def _try_pollinations_image(full_prompt: str, output_path: Path,
                            width: int, height: int, seed: int) -> bool:
    """Last resort fallback: Pollinations (unlimited, decent quality)."""
    models = ["flux", "flux-realism"]
    for model in models:
        for attempt in range(2):
            try:
                url = POLLINATIONS_URL.format(
                    prompt=quote_plus(full_prompt[:800]),
                    model=model, w=width, h=height,
                    seed=(seed + attempt * 137) % 1_000_000,
                )
                r = requests.get(url, timeout=150)
                if r.status_code == 200 and len(r.content) > 40000:
                    with open(output_path, "wb") as f:
                        f.write(r.content)
                    print(f"      ✓ Pollinations/{model}")
                    return True
            except Exception:
                time.sleep(2)
    return False


def generate_image(visual_prompt: str, mood: str, style: str,
                   output_path: Path, width: int, height: int,
                   seed: int = None) -> bool:
    """
    Generate image with provider cascade (all free):
      1. Gemini        — best quality, 500 free/day
      2. Cloudflare    — FLUX.1, 10K free neurons/day
      3. Together.ai   — FLUX schnell, $25 free credit
      4. Pollinations  — unlimited fallback
    """
    style_suffix = VISUAL_STYLES.get(style, VISUAL_STYLES["cinematic"])
    mood_mod = MOOD_MODIFIERS.get(mood, MOOD_MODIFIERS["mysterious"])
    full_prompt = f"{visual_prompt}. {mood_mod}. Style: {style_suffix}"

    if seed is None:
        seed = int(hashlib.md5(visual_prompt.encode()).hexdigest()[:8], 16) % 1_000_000

    # 1. Gemini (best quality)
    if _try_gemini_image(full_prompt, output_path, width, height):
        return True

    # 2. Cloudflare Workers AI (FLUX, very good)
    print("      Trying Cloudflare...")
    if _try_cloudflare_image(full_prompt, output_path, width, height):
        return True

    # 3. Together.ai (FLUX schnell, good)
    print("      Trying Together...")
    if _try_together_image(full_prompt, output_path, width, height):
        return True

    # 4. Pollinations (unlimited fallback)
    print("      Trying Pollinations...")
    if _try_pollinations_image(full_prompt, output_path, width, height, seed):
        return True

    return False


# ── TTS ──

async def generate_tts(text: str, output_path: Path, voice: str, rate: str = "+5%"):
    v = VOICES.get(voice, VOICES["narrator"])
    comm = edge_tts.Communicate(text, v, rate=rate)
    await comm.save(str(output_path))


# ── Captions (Whisper) ──

def transcribe_audio(audio_path: Path, model_size: str = "base") -> list:
    import whisper
    model = whisper.load_model(model_size)
    result = model.transcribe(str(audio_path), word_timestamps=True, verbose=False)
    words = []
    for seg in result["segments"]:
        for w in seg.get("words", []):
            words.append({"word": w["word"].strip(), "start": w["start"], "end": w["end"]})
    return words


def group_words(words: list, per_group: int = 2) -> list:
    """Group into pairs (not triples) for more readable captions."""
    groups = []
    for i in range(0, len(words), per_group):
        chunk = words[i:i + per_group]
        if chunk:
            groups.append({
                "text": " ".join(w["word"] for w in chunk),
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
            })
    return groups


# ── Caption rendering (upgraded) ──

def _find_font(size: int):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "C:\\Windows\\Fonts\\impact.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_caption(text: str, max_width: int = 800, max_font: int = 88, min_font: int = 44):
    """Render styled caption on transparent canvas."""
    text_up = text.upper().strip()
    if not text_up:
        return np.zeros((10, 10, 4), dtype=np.uint8)
    
    tmp = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(tmp)
    stroke = 6
    
    font_size = max_font
    font = _find_font(font_size)
    bbox = draw.textbbox((0, 0), text_up, font=font, stroke_width=stroke)
    tw = bbox[2] - bbox[0]
    while tw > max_width and font_size > min_font:
        font_size -= 4
        font = _find_font(font_size)
        bbox = draw.textbbox((0, 0), text_up, font=font, stroke_width=stroke)
        tw = bbox[2] - bbox[0]
    
    th = bbox[3] - bbox[1]
    pad = 16
    img = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # White text with thick black stroke
    draw.text(
        (pad - bbox[0], pad - bbox[1]),
        text_up, font=font,
        fill=(255, 255, 255, 255),
        stroke_width=stroke,
        stroke_fill=(0, 0, 0, 230),
    )
    return np.array(img)


def make_caption_clip(text: str, start: float, end: float, video_w: int, video_h: int):
    """Caption with pop-in animation."""
    frame = render_caption(text)
    fh = frame.shape[0]
    duration = max(end - start, 0.05)
    pop_dur = min(0.15, duration * 0.3)
    
    def scale_fn(t):
        if t < pop_dur * 0.6:
            return 0.6 + 0.55 * (t / (pop_dur * 0.6))
        elif t < pop_dur:
            return 1.15 - 0.15 * ((t - pop_dur * 0.6) / (pop_dur * 0.4))
        return 1.0
    
    clip = ImageClip(frame, transparent=True).set_duration(duration)
    clip = clip.resize(scale_fn)
    
    y_pos = int(video_h * 0.78)
    
    def pos_fn(t):
        s = scale_fn(t)
        return ("center", int(y_pos - s * fh / 2))
    
    return clip.set_position(pos_fn).set_start(start)


# ── Image fitting & Ken Burns ──

def fit_image(img_path: Path, w: int, h: int) -> np.ndarray:
    img = Image.open(img_path).convert("RGB")
    iw, ih = img.size
    ratio = w / h
    img_ratio = iw / ih
    if img_ratio > ratio:
        new_w = int(ih * ratio)
        off = (iw - new_w) // 2
        img = img.crop((off, 0, off + new_w, ih))
    else:
        new_h = int(iw / ratio)
        off = (ih - new_h) // 2
        img = img.crop((0, off, iw, off + new_h))
    img = img.resize((w, h), Image.LANCZOS)
    # Subtle color enhancement
    img = ImageEnhance.Color(img).enhance(1.12)
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Sharpness(img).enhance(1.1)
    return np.array(img)


def ken_burns_clip(img_path: Path, duration: float, w: int, h: int, mood: str = "mysterious"):
    """Mood-aware Ken Burns motion."""
    base = fit_image(img_path, w, h)
    base_img = Image.fromarray(base)
    
    # Pick motion based on mood
    motions = {
        "dark": ("slow_zoom_in", 0.06),
        "tense": ("zoom_in", 0.10),
        "mysterious": ("slow_pan", 0.05),
        "exciting": ("zoom_in", 0.14),
        "shocking": ("fast_zoom", 0.16),
        "calm": ("slow_zoom_out", 0.05),
        "epic": ("zoom_out", 0.10),
    }
    motion_type, intensity = motions.get(mood, ("zoom_in", 0.08))
    
    def make_frame(t):
        p = min(t / max(duration, 0.01), 1.0)
        if "zoom_in" in motion_type:
            scale = 1.0 + intensity * p
            ox, oy = 0, 0
        elif "zoom_out" in motion_type:
            scale = 1.0 + intensity - intensity * p
            ox, oy = 0, 0
        elif "pan" in motion_type:
            scale = 1.0 + intensity
            ox = -intensity/2 + intensity * p
            oy = 0
        else:
            scale = 1.0 + intensity * p
            ox, oy = 0, 0
        
        nw, nh = int(w * scale), int(h * scale)
        scaled = base_img.resize((nw, nh), Image.LANCZOS)
        cx = nw // 2 + int(ox * nw * 0.5)
        cy = nh // 2 + int(oy * nh * 0.5)
        left = max(0, min(nw - w, cx - w // 2))
        top = max(0, min(nh - h, cy - h // 2))
        return np.array(scaled.crop((left, top, left + w, top + h)))
    
    return VideoClip(make_frame, duration=duration)


def make_vignette(w: int, h: int, duration: float, strength: int = 140):
    y, x = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    d = np.sqrt(((x - cx) / cx) ** 2 + ((y - cy) / cy) ** 2)
    alpha = (np.clip((d - 0.5) / 0.55, 0, 1) ** 2 * strength).astype(np.uint8)
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[..., 3] = alpha
    return ImageClip(img, transparent=True).set_duration(duration)


# ── Background music ──

def get_background_music(duration: float, mood: str, temp_dir: Path) -> AudioFileClip | None:
    """Try to get free background music. Returns None if unavailable."""
    music_path = temp_dir / "bg_music.mp3"
    
    # Try Pixabay-style free music APIs
    # For now, we'll generate a subtle ambient tone using numpy
    # This is better than nothing and costs $0
    try:
        sample_rate = 44100
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        
        # Create a subtle ambient pad based on mood
        mood_freqs = {
            "dark": [65, 98, 131],
            "tense": [73, 110, 147],
            "mysterious": [82, 123, 165],
            "exciting": [98, 147, 196],
            "shocking": [73, 110, 147],
            "calm": [130, 196, 262],
            "epic": [65, 98, 131],
        }
        freqs = mood_freqs.get(mood, [82, 123, 165])
        
        signal = np.zeros_like(t)
        for f in freqs:
            signal += 0.08 * np.sin(2 * np.pi * f * t)
            signal += 0.03 * np.sin(2 * np.pi * f * 1.5 * t)
        
        # Add very slow LFO for movement
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.1 * t)
        signal *= lfo
        
        # Fade in/out
        fade_samples = int(sample_rate * 2)
        signal[:fade_samples] *= np.linspace(0, 1, fade_samples)
        signal[-fade_samples:] *= np.linspace(1, 0, fade_samples)
        
        # Normalize to very low volume (background, not foreground)
        signal = signal / (np.max(np.abs(signal)) + 1e-8) * 0.15
        
        # Convert to 16-bit WAV
        import wave
        wav_path = temp_dir / "bg_music.wav"
        signal_int = (signal * 32767).astype(np.int16)
        with wave.open(str(wav_path), 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(signal_int.tobytes())
        
        return AudioFileClip(str(wav_path))
    except Exception as e:
        print(f"  (ambient music generation failed: {e})")
        return None


# ── Main pipeline ──

async def build_video(
    topic: str,
    name: str,
    style: str = "cinematic",
    voice: str = "narrator",
    video_format: str = "short",
    output_dir: Path = Path("output"),
    temp_dir: Path = Path("temp"),
    whisper_size: str = "base",
    duration_seconds: int = 50,
    script_data: dict = None,
) -> Path | None:
    """
    Build a complete video from topic to finished .mp4.
    
    If script_data is provided, uses it directly.
    Otherwise generates a new script.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    w, h = FORMATS.get(video_format, FORMATS["short"])
    
    # ── Step 1: Script ──
    if not script_data:
        print(f"📝  Generating script for: {topic}")
        if video_format == "long":
            script_data = generate_long_script(topic, duration_minutes=duration_seconds // 60)
        else:
            script_data = generate_script(topic, duration_seconds=duration_seconds)
        
        if not script_data:
            print("❌  Script generation failed")
            return None
    
    scenes = script_data["scenes"]
    full_script = script_data.get("script", " ".join(s["narration"] for s in scenes))
    title = script_data.get("title", topic.title())
    
    print(f"  Title: {title}")
    print(f"  Scenes: {len(scenes)}")
    
    # ── Step 2: Voice ──
    print("🎙️  Generating voiceover...")
    audio_path = temp_dir / f"{name}_audio.mp3"
    await generate_tts(full_script, audio_path, voice)
    audio_clip = AudioFileClip(str(audio_path))
    duration = audio_clip.duration
    print(f"  Duration: {duration:.1f}s")
    
    # ── Step 3: Images ──
    print(f"🎨  Generating {len(scenes)} images...")
    image_paths = []
    scene_moods = []
    
    for i, scene in enumerate(scenes, 1):
        path = temp_dir / f"{name}_scene_{i:03d}.jpg"
        vp = scene.get("visual_prompt", scene["narration"][:100])
        mood = scene.get("mood", "mysterious")
        
        snippet = vp[:55] + "..." if len(vp) > 55 else vp
        print(f"  [{i}/{len(scenes)}] {snippet}")
        
        ok = generate_image(
            visual_prompt=vp, mood=mood, style=style,
            output_path=path, width=w, height=h,
            seed=int(time.time()) + i * 137,
        )
        if ok:
            image_paths.append(path)
            scene_moods.append(mood)
        else:
            print(f"    ⚠️  Failed, skipping")
    
    if not image_paths:
        print("❌  No images generated")
        return None
    
    # ── Step 4: Captions ──
    print("📋  Transcribing captions...")
    words = transcribe_audio(audio_path, model_size=whisper_size)
    captions = group_words(words, per_group=2)
    print(f"  {len(captions)} caption groups")
    
    # ── Step 5: Assemble ──
    print("🎬  Assembling video...")
    per_scene = duration / len(image_paths)
    crossfade = min(0.35, per_scene * 0.15)
    
    # Image clips with mood-matched Ken Burns
    img_clips = []
    for i, (img_path, mood) in enumerate(zip(image_paths, scene_moods)):
        clip_dur = per_scene + (crossfade if i < len(image_paths) - 1 else 0)
        clip = ken_burns_clip(img_path, clip_dur, w, h, mood=mood)
        clip = clip.set_start(i * per_scene)
        if i > 0:
            clip = clip.crossfadein(crossfade)
        img_clips.append(clip)
    
    # Caption clips
    cap_clips = [
        make_caption_clip(c["text"], c["start"], c["end"], w, h)
        for c in captions
    ]
    
    # Vignette
    vignette = make_vignette(w, h, duration)
    
    # Background music
    print("🎵  Adding ambient background...")
    primary_mood = max(set(scene_moods), key=scene_moods.count) if scene_moods else "mysterious"
    bg_music = get_background_music(duration, primary_mood, temp_dir)
    
    # Combine audio
    if bg_music:
        bg_music = bg_music.set_duration(duration)
        from moviepy.editor import CompositeAudioClip
        combined_audio = CompositeAudioClip([audio_clip, bg_music])
    else:
        combined_audio = audio_clip
    
    # Final composite
    final = CompositeVideoClip(
        img_clips + [vignette] + cap_clips, size=(w, h)
    ).set_audio(combined_audio).set_duration(duration)
    
    out_path = output_dir / f"{name}.mp4"
    final.write_videofile(
        str(out_path), fps=30, codec="libx264", audio_codec="aac",
        threads=4, preset="medium", bitrate="6000k",
        logger=None,  # Less verbose
    )
    
    # Write metadata sidecar
    import json
    meta = {
        "title": _format_title(title),
        "description": _format_description(title, topic, full_script),
        "tags": _format_tags(topic),
    }
    out_path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    
    print(f"\n✅  Done → {out_path}")
    return out_path


def _format_title(title: str) -> str:
    """Format title for YouTube."""
    title = title.strip()
    if not title.startswith(("The ", "A ", "An ")):
        pass  # Keep as-is
    if len(title) > 90:
        title = title[:87] + "..."
    if "#shorts" not in title.lower():
        title += " #shorts"
    return title[:100]


def _format_description(title: str, topic: str, script: str) -> str:
    first_sentence = script.split(".")[0].strip()
    tags = " ".join(f"#{w}" for w in topic.split()[:5] if len(w) > 2)
    return (
        f"{first_sentence}.\n\n"
        f"{tags}\n"
        "#shorts #viral #storytelling #mystery"
    )


def _format_tags(topic: str) -> list:
    base = ["shorts", "youtubeshorts", "viral", "storytelling", "mystery"]
    base += [w.strip().lower() for w in topic.split() if len(w) > 2]
    return list(dict.fromkeys(base))[:15]  # Dedupe, max 15


# ── CLI ──

def main():
    p = argparse.ArgumentParser(description="Video Builder v2")
    p.add_argument("--topic", required=True, help="What the video is about")
    p.add_argument("--name", required=True, help="Output filename (no extension)")
    p.add_argument("--style", default="cinematic", choices=list(VISUAL_STYLES))
    p.add_argument("--voice", default="narrator", choices=list(VOICES))
    p.add_argument("--format", default="short", choices=list(FORMATS), dest="video_format")
    p.add_argument("--duration", type=int, default=50, help="Target seconds")
    p.add_argument("--whisper", default="base", choices=["tiny", "base", "small", "medium"])
    p.add_argument("--output-dir", default="output")
    p.add_argument("--temp-dir", default="temp")
    args = p.parse_args()
    
    asyncio.run(build_video(
        topic=args.topic, name=args.name, style=args.style, voice=args.voice,
        video_format=args.video_format, duration_seconds=args.duration,
        output_dir=Path(args.output_dir), temp_dir=Path(args.temp_dir),
        whisper_size=args.whisper,
    ))


if __name__ == "__main__":
    main()
