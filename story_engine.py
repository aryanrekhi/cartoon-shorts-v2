"""
Story Engine v2.2 — Research-backed viral script generation.
=============================================================
Built from analysis of 100K+ viral Shorts (2026 data):
  • 5-beat structure: Hook → Setup → Twist (But...) → Escalation (Therefore...) → Loop-Cliffhanger
  • Optimal length: 35-45 seconds (85-110 words)
  • Looping endings that flow back into the opening
  • Specific numbers, names, dates in every hook
  • "But/Therefore" chains instead of "and then"
  • Visual prompts generated separately (never raw narration → image gen)
"""

import re
import logging
from llm_client import ask

log = logging.getLogger(__name__)


# ── The prompt that makes or breaks everything ──

SCRIPT_SYSTEM = """You are the #1 viral YouTube Shorts scriptwriter in the world.
You write mystery/documentary narration that gets millions of views.

STRUCTURE (follow this EXACTLY — 5 beats):

BEAT 1 — THE HOOK (first 2 sentences):
Start with the most SHOCKING specific detail. Use a real number, date, or name.
Example: "In nineteen twenty two, a German farmer noticed footprints in the snow leading TO his farmhouse. But none leading away."
This must make it IMPOSSIBLE to scroll past.

BEAT 2 — THE SETUP (2-3 sentences):
Give context. Who, where, when. Make the viewer understand why this matters.
Use "But..." to introduce the first complication.

BEAT 3 — THE TWIST (2-3 sentences):
Reveal something that changes everything. Start with "But" or "Then" or "What nobody expected was..."
This is where the story turns.

BEAT 4 — THE ESCALATION (2-3 sentences):
Things get worse or weirder. Use "Therefore..." or "And that's when..." to chain events.
Add one more specific, shocking detail.

BEAT 5 — THE LOOP-CLIFFHANGER (1-2 sentences):
End with an unsettling question or statement that CONNECTS BACK to the hook.
The viewer should feel the urge to watch again.
Example: "And those footprints in the snow? They were made by someone INSIDE the house."

CRITICAL RULES:
- EXACTLY {words} words. Count them. Not 50, not 200. Exactly {words}.
- Every sentence under 12 words
- SPECIFIC details only: real names, real dates, real places, real numbers
- NEVER say "many people", "some believe", "experts say" — NAME them
- Spell out ALL numbers as words (nineteen twenty two, not 1922)
- Use "But..." and "Therefore..." to connect beats — NEVER "and then"
- No emojis, no hashtags, no [SFX], no labels, no "Scene 1:"
- Output ONLY the spoken narration. Nothing else. No titles. No formatting."""


SCRIPT_PROMPT = """Write a {words}-word narration script about:
{topic}

Remember:
- Hook with a SPECIFIC shocking detail (name, date, number)
- Build with "But..." and "Therefore..." connections
- End with a cliffhanger that loops back to the hook
- Exactly {words} words
- ONLY output the narration, nothing else."""


VISUAL_SYSTEM = """You are a cinematographer writing shot descriptions for an AI image generator.
Given narration, describe what to SHOW on screen in 30-45 words.

RULES:
- Describe a SPECIFIC visual scene like a movie shot
- Include: subject, action, environment, camera angle, lighting
- NEVER include any text, words, letters, writing, or numbers in the description
- NEVER describe captions, titles, or overlays
- Focus on PEOPLE, PLACES, OBJECTS, EMOTIONS, ATMOSPHERE
- Make each scene visually DIFFERENT from the others
- Be cinematic: dramatic angles, striking lighting, vivid details
- Output ONLY the visual description, nothing else."""


def generate_script(topic: str, duration_seconds: int = 40) -> dict | None:
    """
    Generate a viral-optimized script with visual prompts.
    Returns: {title, script, scenes: [{narration, visual_prompt, mood}]}
    """
    word_target = max(85, min(130, int(duration_seconds * 2.5)))

    # ── Step 1: Generate narration ──
    system = SCRIPT_SYSTEM.format(words=word_target)
    prompt = SCRIPT_PROMPT.format(words=word_target, topic=topic)

    narration = ask(prompt, system=system, temperature=0.9, max_tokens=1500, retries=2)
    if not narration or len(narration.split()) < 30:
        log.warning("Script generation failed or too short")
        return None

    narration = _clean_narration(narration)
    if len(narration.split()) < 30:
        return None

    # ── Step 2: Split into scenes ──
    scenes_text = _split_into_scenes(narration, target_words=18)
    if len(scenes_text) < 4:
        # Try smaller chunks if we got too few scenes
        scenes_text = _split_into_scenes(narration, target_words=14)
    if len(scenes_text) < 3:
        return None

    # ── Step 3: Generate visual prompts ──
    scenes = []
    for i, scene_narration in enumerate(scenes_text):
        visual = _generate_visual_prompt(scene_narration, topic, i, len(scenes_text))
        mood = _detect_mood(scene_narration, i, len(scenes_text))
        scenes.append({
            "narration": scene_narration,
            "visual_prompt": visual,
            "mood": mood,
        })

    title = _generate_title(narration, topic)

    return {
        "title": title,
        "script": narration,
        "scenes": scenes,
    }


def generate_long_script(topic: str, duration_minutes: int = 8) -> dict | None:
    """Generate a long-form documentary script (5-15 min)."""
    word_target = int(duration_minutes * 60 * 2.5)

    system = (
        "You are an elite documentary narrator. Write ONLY spoken narration.\n"
        "Rules:\n"
        f"- About {word_target} words total\n"
        "- Short sentences, under 15 words each\n"
        "- Start with the most shocking detail\n"
        "- Use SPECIFIC names, dates, places, numbers\n"
        "- Connect ideas with 'But...' and 'Therefore...' not 'and then'\n"
        "- Structure: Shocking hook → Origin story → 3 escalating revelations → Haunting conclusion\n"
        "- Spell out all numbers as words\n"
        "- No emojis, no stage directions, ONLY narration"
    )
    prompt = f"Write a {word_target}-word documentary narration about:\n{topic}\n\nOutput ONLY the narration."

    narration = ask(prompt, system=system, temperature=0.8, max_tokens=4000, retries=2)
    if not narration or len(narration.split()) < 100:
        return None

    narration = _clean_narration(narration)
    scenes_text = _split_into_scenes(narration, target_words=25)

    scenes = []
    for i, sn in enumerate(scenes_text):
        visual = _generate_visual_prompt(sn, topic, i, len(scenes_text))
        mood = _detect_mood(sn, i, len(scenes_text))
        scenes.append({"narration": sn, "visual_prompt": visual, "mood": mood})

    title = _generate_title(narration, topic)
    return {"title": title, "script": narration, "scenes": scenes}


# ── Helpers ──

def _clean_narration(text: str) -> str:
    """Remove formatting artifacts."""
    text = text.strip()
    # Remove markdown, scene labels, titles
    text = re.sub(r'^#+\s+.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\*?\*?\s*(Scene|Beat|Hook|Setup|Twist|Climax|Escalation|Cliffhanger|Outro|Intro|Opening|Closing|Title|TITLE)\s*\d*\s*[:—-]?\s*\*?\*?', '', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^(Title|TITLE)\s*:.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*+', '', text)  # Remove bold markers
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    text = ' '.join(lines)
    text = re.sub(r'\s+', ' ', text).strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    return text


def _split_into_scenes(script: str, target_words: int = 18) -> list:
    """Split by sentence boundaries, grouping to target word count per scene."""
    sentences = re.split(r'(?<=[.!?])\s+', script.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    scenes = []
    current = ""
    for sent in sentences:
        current_words = len(current.split()) if current else 0
        sent_words = len(sent.split())
        if current_words + sent_words <= target_words + 5:
            current = (current + " " + sent).strip()
        else:
            if current:
                scenes.append(current)
            current = sent
    if current:
        scenes.append(current)

    return scenes


def _generate_visual_prompt(narration: str, topic: str, scene_index: int, total_scenes: int) -> str:
    """Generate a cinematic visual prompt. NEVER sends raw narration to image gen."""
    position = "opening" if scene_index == 0 else ("climax" if scene_index == total_scenes - 1 else f"scene {scene_index + 1} of {total_scenes}")

    prompt = (
        f"Topic: {topic}\n"
        f"Position: {position}\n"
        f"Narration being spoken: \"{narration}\"\n\n"
        f"Describe the VISUAL scene to show (30-45 words, NO text/words in the image):"
    )

    result = ask(prompt, system=VISUAL_SYSTEM, temperature=0.8, max_tokens=200, retries=1)
    if result:
        line = result.split('\n')[0].strip().strip('"').strip("'")
        # Make sure it doesn't contain instructions to render text
        line = re.sub(r'(?i)\b(text|words?|letters?|caption|title|subtitle|overlay|reading|says?|written)\b[^,]*,?', '', line)
        if len(line) > 20:
            return line.strip().strip(',')

    # Fallback: topic-based prompt, not narration-based
    return f"Cinematic dramatic scene related to {topic[:50]}, detailed environment, atmospheric lighting, no text, film still quality"


def _detect_mood(narration: str, scene_index: int, total_scenes: int) -> str:
    """Mood detection from content and position."""
    text = narration.lower()
    if scene_index == 0:
        return "tense"  # Hook should feel urgent
    if scene_index == total_scenes - 1:
        return "dark"  # Cliffhanger should feel unsettling
    if scene_index == total_scenes - 2:
        return "shocking"  # Escalation

    if any(w in text for w in ["dead", "killed", "murder", "death", "blood", "body", "bodies"]):
        return "dark"
    if any(w in text for w in ["but", "however", "strange", "bizarre", "unexplained", "vanish"]):
        return "mysterious"
    if any(w in text for w in ["never", "impossible", "shocking", "secret", "hidden", "truth"]):
        return "tense"
    if any(w in text for w in ["billion", "million", "massive", "ancient", "empire", "vast"]):
        return "epic"
    return "mysterious"


def _generate_title(narration: str, topic: str) -> str:
    """Generate a clickable title."""
    first = narration.split('.')[0].strip()
    if 15 < len(first) < 65:
        return first
    title = topic.split('—')[0].strip() if '—' in topic else topic
    return title[:65] if len(title) > 65 else title


# ── Self-test ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    result = generate_script("The Hinterkaifeck murders — six people killed on a German farm in 1922 and the killer lived with the bodies for days")
    if result:
        print(f"Title: {result['title']}")
        print(f"Words: {len(result['script'].split())}")
        print(f"Scenes: {len(result['scenes'])}")
        print(f"\nFull script:\n{result['script']}")
        for i, s in enumerate(result['scenes'], 1):
            print(f"\n  Scene {i}: [{s['mood']}]")
            print(f"    Say: {s['narration'][:60]}...")
            print(f"    Show: {s['visual_prompt'][:60]}...")
