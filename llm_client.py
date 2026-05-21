"""
Multi-LLM client with failover.
Tries: Gemini → Groq → Cerebras → Pollinations (free fallback).
All free. Combined rate limits = high throughput.
"""

import os
import time
import json
import random
import logging
import urllib.parse
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

# ── Provider configs ──

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
CEREBRAS_MODELS = ["llama3.1-8b", "llama-3.3-70b"]
POLLINATIONS_MODELS = ["openai", "mistral"]

# ── HTTP helpers ──

def _post_json(url, payload, headers, timeout=60):
    headers = dict(headers or {})
    headers.setdefault("User-Agent", "cartoon-shorts/2.0")
    headers.setdefault("Accept", "application/json")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def _get_text(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "cartoon-shorts/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")

# ── Providers ──

def _try_gemini(prompt, system=None, temperature=0.85, max_tokens=2000):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    full = f"{system}\n\n{prompt}" if system else prompt
    for model in GEMINI_MODELS:
        try:
            resp = _post_json(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                {
                    "contents": [{"parts": [{"text": full}]}],
                    "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
                },
                {"Content-Type": "application/json"},
                timeout=45,
            )
            text = resp["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text and len(text) > 30:
                return text
        except urllib.error.HTTPError as e:
            if e.code == 429:
                continue
        except Exception:
            continue
    return None

def _try_groq(prompt, system=None, temperature=0.85, max_tokens=2000):
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    for model in GROQ_MODELS:
        try:
            resp = _post_json(
                "https://api.groq.com/openai/v1/chat/completions",
                {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=30,
            )
            text = resp["choices"][0]["message"]["content"].strip()
            if text and len(text) > 30:
                return text
        except urllib.error.HTTPError as e:
            if e.code == 429:
                continue
        except Exception:
            continue
    return None

def _try_cerebras(prompt, system=None, temperature=0.85, max_tokens=2000):
    key = os.environ.get("CEREBRAS_API_KEY", "").strip()
    if not key:
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    for model in CEREBRAS_MODELS:
        try:
            resp = _post_json(
                "https://api.cerebras.ai/v1/chat/completions",
                {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                timeout=30,
            )
            text = resp["choices"][0]["message"]["content"].strip()
            if text and len(text) > 30:
                return text
        except urllib.error.HTTPError as e:
            if e.code == 429:
                continue
        except Exception:
            continue
    return None

def _try_pollinations(prompt, system=None, temperature=0.85, max_tokens=2000):
    full = f"{system}\n\n{prompt}" if system else prompt
    encoded = urllib.parse.quote(full[:3000])
    for model in POLLINATIONS_MODELS:
        for attempt in range(2):
            try:
                text = _get_text(
                    f"https://text.pollinations.ai/{encoded}?model={model}", timeout=60
                ).strip()
                if text and len(text) > 50:
                    return text
            except Exception:
                time.sleep(2 + random.random() * 2)
    return None

# ── Public API ──

PROVIDERS = [
    ("gemini", _try_gemini),
    ("groq", _try_groq),
    ("cerebras", _try_cerebras),
    ("pollinations", _try_pollinations),
]

def ask(prompt, system=None, temperature=0.85, max_tokens=2000, retries=2):
    """Try each provider in order. Returns first non-empty response."""
    for cycle in range(retries):
        if cycle > 0:
            time.sleep(3 + cycle * 2)
        for name, fn in PROVIDERS:
            try:
                result = fn(prompt, system=system, temperature=temperature, max_tokens=max_tokens)
                if result:
                    log.debug(f"  [{name}] ok")
                    return result
            except Exception as e:
                log.debug(f"  [{name}] {e}")
    return None
