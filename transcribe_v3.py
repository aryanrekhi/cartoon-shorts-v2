"""
transcribe_v3.py — drop-in transcription module for V2 pipeline.

Verified June 2026: faster-whisper is the GOAT free transcription option.
- 4-8x faster than openai-whisper at IDENTICAL accuracy
- Lower memory (int8 quantization uses ~50% less than float32)
- Same model weights, just CTranslate2-optimized backend
- CPU-friendly (works fine without GPU)
- Word-level timestamps work the same way
"""

import os
import sys
import logging

log = logging.getLogger(__name__)


def _have_faster_whisper():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _have_openai_whisper():
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _transcribe_faster(audio_path, model_size="base", device="cpu", compute_type=None):
    """faster-whisper backend: 4-8x faster than openai-whisper at same accuracy."""
    from faster_whisper import WhisperModel

    if compute_type is None:
        compute_type = "float16" if device == "cuda" else "int8"

    print(f"  Loading faster-whisper ({model_size}, device={device}, compute={compute_type})...")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
    )

    words = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                words.append({
                    "word": w.word.strip(),
                    "start": float(w.start),
                    "end": float(w.end),
                })
    return words


def _transcribe_openai(audio_path, model_size="base"):
    """Original V2 behaviour — fallback only."""
    import whisper
    print(f"  Loading openai-whisper ({model_size}) [install faster-whisper for speedup]...")
    model = whisper.load_model(model_size)
    result = model.transcribe(str(audio_path), word_timestamps=True, verbose=False)
    words = []
    for segment in result["segments"]:
        for w in segment.get("words", []):
            words.append({
                "word": w["word"].strip(),
                "start": float(w["start"]),
                "end": float(w["end"]),
            })
    return words


def transcribe(audio_path, model_size="base", device=None, compute_type=None):
    """
    Transcribe audio to word-level timestamps.
    Auto-detects backend: prefers faster-whisper, falls back to openai-whisper.
    Returns: list of {"word": str, "start": float, "end": float}
    """
    if device is None:
        device = os.environ.get("WHISPER_DEVICE", "cpu").lower()
    if device not in ("cpu", "cuda"):
        device = "cpu"

    if _have_faster_whisper():
        try:
            return _transcribe_faster(audio_path, model_size=model_size, device=device, compute_type=compute_type)
        except Exception as e:
            log.warning(f"faster-whisper failed ({type(e).__name__}: {e}), falling back to openai-whisper")

    if _have_openai_whisper():
        if model_size.startswith("distil-"):
            log.warning(f"openai-whisper doesn't support {model_size}, using 'base' instead")
            model_size = "base"
        return _transcribe_openai(audio_path, model_size=model_size)

    raise ImportError(
        "No whisper backend installed. Install with:\n"
        "  pip install faster-whisper   (RECOMMENDED — 4-8x faster)\n"
        "  pip install openai-whisper   (slower, but works)"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python transcribe_v3.py <audio_file> [model_size]")
        sys.exit(1)

    audio = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "base"

    print(f"\nBackend availability:")
    print(f"  faster-whisper: {'YES (will use this)' if _have_faster_whisper() else 'no'}")
    print(f"  openai-whisper: {'YES' if _have_openai_whisper() else 'no'}")

    print(f"\nTranscribing {audio} with {model}...")
    import time
    t0 = time.time()
    words = transcribe(audio, model_size=model)
    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s — {len(words)} words")

    if words:
        print(f"\nFirst 10 words:")
        for w in words[:10]:
            print(f"  [{w['start']:6.2f} -> {w['end']:6.2f}]  {w['word']}")
