"""
Story Engine v2.1 — Rebuilt for reliability.
=============================================
The v2.0 approach (asking LLMs for JSON) was fragile — LLMs mangle JSON
and the fallback was garbage (3 vague scenes, 20 seconds).

New approach: TWO STEPS, each simple and reliable.
  Step 1: Generate a PLAIN TEXT narration script (just spoken words)
  Step 2: For each scene, generate a visual prompt SEPARATELY

This way each LLM call is simple and hard to screw up.
"""

import re
import logging
from llm_client import ask

log = logging.getLogger(__name__)


def generate_script(topic: str, duration_seconds: int = 55) -> dict | None:
    """
    Generate a structured script with scenes and visual prompts.
    Returns dict: {title, script, scenes: [{narration, visual_prompt, mood}]}
    """
    word_target = int(duration_seconds * 2.5)

    # ── Step 1: Generate narration (plain text, no JSON, no formatting) ──
    system = (
        "You are an elite short-form scriptwriter for viral YouTube Shorts. "
        "Write ONLY the narrator's spoken words. Nothing else.\n\n"
        "RULES:\n"
        "- Exactly {words} words, no more, no less\n"
        "- Short punchy sentences, under 12 words each\n"
        "- Start with a HOOK that makes scrolling impossible\n"
        "- Use SPECIFIC details: real names, real dates, real places, real numbers\n"
        "- NEVER be vague. Never say 'many people' or 'some say'\n"
        "- Build tension sentence by sentence\n"
        "- End with a question or chilling statement\n"
        "- Spell out all numbers as words (nineteen sixty one, not 1961)\n"
        "- No emojis, no hashtags, no [SFX], no stage directions\n"
        "- ONLY output the narration. No titles, no labels, no scene numbers."
    ).format(words=word_target)

    prompt = (
        f"Write a {word_target}-word narration script about:\n"
        f"{topic}\n\n"
        f"Remember: {word_target} words, specific details, hook first, tension throughout. "
        f"Output ONLY the spoken narration, nothing else."
    )

    narration = ask(prompt, system=system, temperature=0.85, max_tokens=1500, retries=2)
    if not narration or len(narration) < 80:
        log.warning("Script generation failed")
        return None

    # Clean up narration
    narration = _clean_narration(narration)
    if len(narration) < 80:
        return None

    # ── Step 2: Split into scenes ──
    scenes_text = _split_into_scenes(narration, target_chars=110)
    if len(scenes_text) < 3:
        return None

    # ── Step 3: Generate visual prompts for each scene ──
    scenes = []
    for i, scene_narration in enumerate(scenes_text):
        visual = _generate_visual_prompt(scene_narration, topic, i, len(scenes_text))
        mood = _detect_mood(scene_narration, i, len(scenes_text))
        scenes.append({
            "narration": scene_narration,
            "visual_prompt": visual,
            "mood": mood,
        })

    # Generate title
    title = _generate_title(narration, topic)

    return {
        "title": title,
        "script": narration,
        "scenes": scenes,
    }


def generate_long_script(topic: str, duration_minutes: int = 8) -> dict | None:
    """Generate a long-form script (5-15 minutes)."""
    word_target = int(duration_minutes * 60 * 2.5)

    system = (
        "You are an elite documentary scriptwriter. "
        "Write ONLY the narrator's spoken words for an {mins}-minute documentary.\n\n"
        "RULES:\n"
        "- About {words} words total\n"
        "- Short sentences, under 15 words each\n"
        "- Start with the most shocking or fascinating detail\n"
        "- Use SPECIFIC names, dates, places, numbers throughout\n"
        "- Structure: Hook, then 3-4 main sections, then conclusion\n"
        "- Each section should reveal something new and surprising\n"
        "- Spell out numbers as words\n"
        "- No emojis, no stage directions, ONLY narration"
    ).format(mins=duration_minutes, words=word_target)

    prompt = (
        f"Write a {word_target}-word documentary narration about:\n{topic}\n\n"
        f"Output ONLY the spoken narration."
    )

    narration = ask(prompt, system=system, temperature=0.8, max_tokens=4000, retries=2)
    if not narration or len(narration) < 200:
        return None

    narration = _clean_narration(narration)
    scenes_text = _split_into_scenes(narration, target_chars=130)

    scenes = []
    for i, sn in enumerate(scenes_text):
        visual = _generate_visual_prompt(sn, topic, i, len(scenes_text))
        mood = _detect_mood(sn, i, len(scenes_text))
        scenes.append({"narration": sn, "visual_prompt": visual, "mood": mood})

    title = _generate_title(narration, topic)
    return {"title": title, "script": narration, "scenes": scenes}


def _clean_narration(text: str) -> str:
    """Remove any formatting artifacts the LLM added."""
    text = text.strip()
    # Remove markdown headers
    text = re.sub(r'^#+\s+.*$', '', text, flags=re.MULTILINE)
    # Remove scene labels like "Scene 1:" or "**Hook:**"
    text = re.sub(r'^\*?\*?\s*(Scene|Hook|Setup|Twist|Climax|Outro|Intro|Opening|Closing)\s*\d*\s*:?\s*\*?\*?', '', text, flags=re.MULTILINE | re.IGNORECASE)
    # Remove "Title: ..." lines
    text = re.sub(r'^(Title|TITLE)\s*:.*$', '', text, flags=re.MULTILINE)
    # Remove empty lines and rejoin
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    text = ' '.join(lines)
    # Remove double spaces
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove quotes if the whole thing is wrapped in them
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    return text


def _split_into_scenes(script: str, target_chars: int = 110) -> list:
    """Split narration into scenes of roughly target_chars length."""
    sentences = re.split(r'(?<=[.!?])\s+', script.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    scenes = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) < target_chars:
            current = (current + " " + sent).strip()
        else:
            if current:
                scenes.append(current)
            current = sent
    if current:
        scenes.append(current)

    return scenes


def _generate_visual_prompt(narration: str, topic: str, scene_index: int, total_scenes: int) -> str:
    """Generate a cinematic visual prompt for one scene. Never sends raw narration to image gen."""
    system = (
        "You are a cinematographer writing shot descriptions for an AI image generator.\n"
        "Given narration text, describe what to SHOW on screen in 25-40 words.\n\n"
        "CRITICAL RULES:\n"
        "- Describe a SPECIFIC visual scene, not abstract concepts\n"
        "- Include: main subject, their action, environment, camera angle, lighting\n"
        "- NEVER include any text, words, letters, numbers, or writing in the image\n"
        "- NEVER describe text overlays, titles, or captions\n"
        "- Focus on PEOPLE, PLACES, OBJECTS, ACTIONS\n"
        "- Be cinematic: describe it like a movie shot\n"
        "- Output ONLY the visual prompt, nothing else"
    )

    position = "opening" if scene_index == 0 else ("closing" if scene_index == total_scenes - 1 else "middle")
    prompt = (
        f"Topic: {topic}\n"
        f"Scene position: {position} ({scene_index + 1} of {total_scenes})\n"
        f"Narration: {narration}\n\n"
        f"Visual prompt (25-40 words, NO text in the image):"
    )

    result = ask(prompt, system=system, temperature=0.8, max_tokens=200, retries=1)
    if result:
        # Take first line, clean up
        line = result.split('\n')[0].strip().strip('"').strip("'")
        if len(line) > 20:
            return line

    # Fallback: create a visual description from the topic, NOT from narration
    return f"Cinematic wide shot related to {topic[:60]}, dramatic lighting, detailed environment, atmospheric, no text"


def _detect_mood(narration: str, scene_index: int, total_scenes: int) -> str:
    """Simple mood detection based on keywords and position."""
    text = narration.lower()

    if scene_index == 0:
        return "mysterious"
    if scene_index == total_scenes - 1:
        return "epic"

    if any(w in text for w in ["dead", "killed", "murder", "death", "blood", "dark", "horror"]):
        return "dark"
    if any(w in text for w in ["strange", "bizarre", "unexplained", "mystery", "vanish", "disappear"]):
        return "mysterious"
    if any(w in text for w in ["never", "impossible", "shocking", "discovered", "revealed", "truth"]):
        return "tense"
    if any(w in text for w in ["billion", "million", "massive", "enormous", "vast", "ancient", "empire"]):
        return "epic"
    if any(w in text for w in ["quiet", "peaceful", "calm", "gentle", "silent"]):
        return "calm"

    return "mysterious"


def _generate_title(narration: str, topic: str) -> str:
    """Generate a catchy title."""
    # Try to use the first sentence as a hook-based title
    first = narration.split('.')[0].strip()
    if 20 < len(first) < 70:
        return first

    # Fallback: clean up the topic
    title = topic.split('—')[0].strip() if '—' in topic else topic
    if len(title) > 70:
        title = title[:67] + "..."
    return title


# ── Self-test ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    result = generate_script("The Dyatlov Pass incident — nine hikers found dead in bizarre circumstances", duration_seconds=50)
    if result:
        print(f"Title: {result['title']}")
        print(f"Script length: {len(result['script'])} chars")
        print(f"Scenes: {len(result['scenes'])}")
        for i, s in enumerate(result['scenes'], 1):
            print(f"\n  Scene {i}:")
            print(f"    Narration: {s['narration'][:60]}...")
            print(f"    Visual: {s['visual_prompt'][:60]}...")
            print(f"    Mood: {s['mood']}")
