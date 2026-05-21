"""
Story Engine v2 — The brain.
=============================
Generates scripts that are actually INTERESTING, with:
  • Structured 5-beat narrative arcs (not vague rambling)
  • Specific details (names, dates, places — not "many murders happened")
  • Scene-by-scene visual direction baked in
  • Hook-first writing that stops the scroll
  • Both short-form (30-60s) and long-form (5-15 min) support

The key insight: the old system asked "write about unsolved mysteries" and got
generic slop. This system provides STRUCTURE and demands SPECIFICS.
"""

import json
import re
import logging
from llm_client import ask

log = logging.getLogger(__name__)

# ── Story templates — these force structure on the LLM ──

TEMPLATES = {
    "mystery_reveal": {
        "description": "A specific mystery with clues that build to a shocking reveal or open question",
        "beats": [
            "HOOK: State the most shocking/bizarre detail of this story in one punchy sentence. Make it impossible to scroll past.",
            "SETUP: When and where did this happen? Name real people, real places, real dates. Set the scene vividly in 2-3 sentences.",
            "ESCALATION: What happened next that made this strange? Build tension with 3-4 specific details that don't add up.",
            "TWIST: Reveal the detail that changes everything. The piece of evidence, the confession, the discovery. 2-3 sentences.",
            "CLIFFHANGER: End with an unsettling question or implication. Leave the viewer thinking. One powerful sentence.",
        ],
    },
    "comparison_explainer": {
        "description": "Every type of X explained, or X vs Y comparison with fascinating details",
        "beats": [
            "HOOK: State the most surprising fact about this topic. 'Most people think X, but Y.'",
            "FOUNDATION: Explain the basics quickly — what is this thing, why does it matter? 2 sentences max.",
            "DEEP DIVE: Walk through 3-5 specific examples/types with one fascinating detail each. Be specific — numbers, names, places.",
            "SURPRISING FACT: The one thing about this topic that shocks people. The counter-intuitive truth.",
            "PAYOFF: Tie it together. What does this mean? Why should the viewer care? End with impact.",
        ],
    },
    "historical_story": {
        "description": "A specific historical event told as a gripping narrative",
        "beats": [
            "HOOK: Drop the viewer into the most dramatic moment. Present tense. Make them FEEL it.",
            "CONTEXT: Pull back. When is this? Who is the main character? What's at stake? 2-3 sentences.",
            "RISING ACTION: Things get worse or more complex. Specific events, specific details. 3-4 sentences.",
            "CLIMAX: The decisive moment. What happened? Be vivid and specific. 2-3 sentences.",
            "AFTERMATH: What was the consequence? How did this change things? End with lasting impact. 1-2 sentences.",
        ],
    },
    "what_if_scenario": {
        "description": "A thought experiment or hypothetical scenario explored with real science/logic",
        "beats": [
            "HOOK: State the wild hypothetical. 'What if X happened tomorrow?'",
            "FIRST CONSEQUENCE: The immediate, obvious effect. Be specific with numbers and scale.",
            "CHAIN REACTION: The second-order effects nobody thinks about. 3-4 surprising consequences.",
            "EXTREME CASE: Take it to the logical extreme. What happens at the end of this chain?",
            "REALITY CHECK: Tie back to reality. Could this actually happen? What's the real risk? End with something unsettling.",
        ],
    },
    "profile_deep_dive": {
        "description": "Deep dive into a person, company, animal, place, or phenomenon",
        "beats": [
            "HOOK: The single most extraordinary fact about this subject. Make jaws drop.",
            "ORIGIN: Where did this come from? The backstory nobody knows. 2-3 sentences.",
            "PEAK: The height of their power/fame/impact. Specific achievements with numbers.",
            "DARK SIDE: The controversy, the failure, the hidden truth. 2-3 sentences.",
            "LEGACY: What remains? What did this change forever? End with perspective.",
        ],
    },
}


def _pick_template(topic: str) -> str:
    """Pick the best story template based on topic keywords."""
    topic_lower = topic.lower()
    if any(w in topic_lower for w in ["mystery", "unsolved", "disappear", "haunted", "strange", "unexplained", "cold case", "crime"]):
        return "mystery_reveal"
    if any(w in topic_lower for w in ["every", "type", "compare", "vs", "versus", "explained", "ranking"]):
        return "comparison_explainer"
    if any(w in topic_lower for w in ["history", "ancient", "war", "battle", "empire", "century", "year"]):
        return "historical_story"
    if any(w in topic_lower for w in ["what if", "hypothetical", "imagine", "could", "would happen"]):
        return "what_if_scenario"
    if any(w in topic_lower for w in ["who", "life of", "story of", "rise", "fall", "genius", "famous"]):
        return "profile_deep_dive"
    # Default to mystery for most topics
    return "mystery_reveal"


def generate_script(topic: str, duration_seconds: int = 50, template_name: str = None) -> dict | None:
    """
    Generate a structured script with scene-by-scene visual directions.
    
    Returns dict with:
        - title: str
        - script: str (full narration text)
        - scenes: list of {narration, visual_prompt, mood}
    
    Or None if generation fails.
    """
    if not template_name:
        template_name = _pick_template(topic)
    template = TEMPLATES[template_name]
    
    word_target = int(duration_seconds * 2.5)
    beats_text = "\n".join(f"  Beat {i+1} — {beat}" for i, beat in enumerate(template["beats"]))
    
    system = (
        "You are an elite short-form video scriptwriter who creates viral content. "
        "You write scripts that are IMPOSSIBLE to scroll past.\n\n"
        "CRITICAL RULES:\n"
        "- Every sentence must be SHORT (under 15 words)\n"
        "- Use SPECIFIC details: real names, real places, real dates, real numbers\n"
        "- NEVER be vague. Never say 'many people' or 'some experts.' Name them.\n"
        "- Write in present tense for immediacy\n"
        "- Spell out numbers as words (nineteen forty seven, not 1947)\n"
        "- No emojis, no [SFX], no stage directions — ONLY spoken narration\n"
        "- Each sentence should make the viewer NEED the next one\n\n"
        "You MUST respond in this EXACT JSON format:\n"
        "{\n"
        '  "title": "Catchy title under 60 chars",\n'
        '  "scenes": [\n'
        '    {\n'
        '      "narration": "The spoken words for this scene. 1-3 sentences.",\n'
        '      "visual_prompt": "Detailed visual description of what to SHOW. Include: subject, action, setting, lighting, mood, camera angle. 20-40 words.",\n'
        '      "mood": "dark|tense|mysterious|exciting|shocking|calm|epic"\n'
        '    }\n'
        "  ]\n"
        "}\n\n"
        "Generate 5-8 scenes total. Each scene's narration should be 1-3 sentences."
    )
    
    prompt = (
        f"TOPIC: {topic}\n"
        f"TARGET LENGTH: {word_target} words total narration (~{duration_seconds} seconds)\n"
        f"STORY STRUCTURE ({template_name}):\n{beats_text}\n\n"
        f"Write a script following this structure. Be SPECIFIC — use real names, "
        f"dates, and places. Research-quality details. Make every word earn its place.\n\n"
        f"Respond with ONLY the JSON object, no markdown, no explanation."
    )
    
    result = ask(prompt, system=system, temperature=0.85, max_tokens=2000, retries=2)
    if not result:
        log.warning("Script generation failed — all providers exhausted")
        return None
    
    return _parse_script_response(result, topic)


def generate_long_script(topic: str, duration_minutes: int = 8) -> dict | None:
    """
    Generate a long-form script (5-15 minutes).
    Uses a chapter structure with multiple story beats.
    """
    word_target = int(duration_minutes * 60 * 2.5)
    
    system = (
        "You are an elite documentary scriptwriter for YouTube. "
        "You create 8-15 minute narrated documentaries that keep viewers glued.\n\n"
        "RULES:\n"
        "- Short, punchy sentences (under 15 words each)\n"
        "- SPECIFIC details: names, dates, places, numbers. Never vague.\n"
        "- Spell out numbers as words\n"
        "- No emojis, no stage directions — only narration\n"
        "- Structure: Hook → Context → 3-4 main sections → Conclusion\n"
        "- Each section should have its own mini-arc\n\n"
        "Respond in this EXACT JSON format:\n"
        "{\n"
        '  "title": "Title under 70 chars",\n'
        '  "scenes": [\n'
        '    {"narration": "...", "visual_prompt": "detailed visual, 20-40 words", "mood": "dark|tense|mysterious|exciting|shocking|calm|epic"}\n'
        "  ]\n"
        "}\n\n"
        "Generate 20-35 scenes. Each scene = 1-3 sentences of narration."
    )
    
    prompt = (
        f"TOPIC: {topic}\n"
        f"TARGET: {word_target} words ({duration_minutes} minute documentary)\n\n"
        f"Write a compelling, research-grade documentary script. "
        f"Use real facts, real stories, real people. Structure it like a Netflix documentary — "
        f"keep the viewer hooked every 30 seconds with a new detail or twist.\n\n"
        f"Respond with ONLY the JSON object."
    )
    
    result = ask(prompt, system=system, temperature=0.8, max_tokens=4000, retries=2)
    if not result:
        return None
    
    return _parse_script_response(result, topic)


def _parse_script_response(raw: str, topic: str) -> dict | None:
    """Parse JSON response from LLM, with fallback extraction."""
    # Try to find JSON in the response
    raw = raw.strip()
    
    # Remove markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from within the text
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                log.warning("Could not parse script JSON — falling back to plain text")
                return _fallback_script(raw, topic)
        else:
            return _fallback_script(raw, topic)
    
    # Validate structure
    if not isinstance(data, dict) or "scenes" not in data:
        return _fallback_script(raw, topic)
    
    scenes = data.get("scenes", [])
    if not scenes or not isinstance(scenes, list):
        return _fallback_script(raw, topic)
    
    # Clean up scenes
    clean_scenes = []
    for s in scenes:
        if isinstance(s, dict) and "narration" in s:
            clean_scenes.append({
                "narration": s["narration"].strip(),
                "visual_prompt": s.get("visual_prompt", "cinematic scene").strip(),
                "mood": s.get("mood", "mysterious").strip(),
            })
    
    if not clean_scenes:
        return _fallback_script(raw, topic)
    
    full_script = " ".join(s["narration"] for s in clean_scenes)
    
    return {
        "title": data.get("title", topic.title())[:100],
        "script": full_script,
        "scenes": clean_scenes,
    }


def _fallback_script(raw_text: str, topic: str) -> dict | None:
    """If JSON parsing fails, treat the raw text as a plain narration script."""
    # Clean up the text
    text = raw_text.strip()
    # Remove any JSON artifacts
    text = re.sub(r'[{}\[\]"]+', '', text)
    text = re.sub(r'\b(narration|visual_prompt|mood|title|scenes)\b\s*:', '', text)
    text = text.strip()
    
    if len(text) < 50:
        return None
    
    # Split into sentences for scenes
    sentences = re.split(r"(?<=[.!?])\s+", text)
    scenes = []
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(current) + len(sent) < 120:
            current = (current + " " + sent).strip()
        else:
            if current:
                scenes.append({
                    "narration": current,
                    "visual_prompt": f"Cinematic scene depicting: {current[:80]}",
                    "mood": "mysterious",
                })
            current = sent
    if current:
        scenes.append({
            "narration": current,
            "visual_prompt": f"Cinematic scene depicting: {current[:80]}",
            "mood": "mysterious",
        })
    
    if not scenes:
        return None
    
    return {
        "title": topic.title()[:100],
        "script": text,
        "scenes": scenes,
    }


def enhance_visual_prompt(narration: str, mood: str = "cinematic", base_prompt: str = "") -> str:
    """
    Convert narration + mood into a detailed visual prompt for image generation.
    Much more detailed than the old 30-word prompts.
    """
    if base_prompt:
        return base_prompt  # Already have a good prompt from structured generation
    
    system = (
        "You are a cinematographer writing shot descriptions for an AI image generator. "
        "Given narration text, write ONE detailed visual prompt (30-50 words) describing "
        "what to SHOW on screen. Include:\n"
        "- Main subject and their action/expression\n"
        "- Setting/environment with specific details\n"
        "- Camera angle (wide, close-up, aerial, low-angle)\n"
        "- Lighting (dramatic shadows, golden hour, neon, moonlight)\n"
        "- Mood/atmosphere\n"
        "Output ONLY the prompt, nothing else."
    )
    
    result = ask(
        f"Narration: {narration}\nMood: {mood}\n\nVisual prompt:",
        system=system, temperature=0.8, max_tokens=200, retries=1,
    )
    
    if result:
        # Take first line only
        return result.split("\n")[0].strip().strip('"').strip("'")
    
    # Fallback
    return f"Cinematic scene: {narration[:100]}, dramatic lighting, detailed, {mood} atmosphere"


# ── Self-test ──

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    
    print("=== Testing Short Script ===")
    result = generate_script("The Dyatlov Pass incident — nine hikers found dead in bizarre circumstances", duration_seconds=50)
    if result:
        print(f"\nTitle: {result['title']}")
        print(f"Scenes: {len(result['scenes'])}")
        for i, s in enumerate(result['scenes'], 1):
            print(f"\n--- Scene {i} ---")
            print(f"  Narration: {s['narration'][:80]}...")
            print(f"  Visual: {s['visual_prompt'][:60]}...")
            print(f"  Mood: {s['mood']}")
    else:
        print("FAILED")
