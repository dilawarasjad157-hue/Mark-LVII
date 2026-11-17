"""Work on whatever text the user just copied: summarise, translate, fix, explain, reply."""

PLUGIN = {
    "name": "clipboard_ai",
    "description": (
        "Act on the text the user just COPIED (Ctrl+C) and put the result back on "
        "the clipboard, ready to paste. Use for 'jo copy kiya hai usko summarize "
        "karo', 'isko English me translate karo', 'grammar theek karo', 'isko "
        "simple samjhao', 'iska reply likho', 'clipboard me kya hai'. If the user "
        "has not copied anything, say so."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "read | summarize | translate | fix | explain | reply | rewrite"},
            "language": {"type": "STRING", "description": "Target language for translate (e.g. English, Urdu, Roman Urdu)"},
            "style": {"type": "STRING", "description": "For rewrite/reply: tone, e.g. formal, friendly, short"},
        },
        "required": ["action"],
    },
}

_PROMPTS = {
    "summarize": "Summarise this in a few clear sentences. Keep the same language as the text.",
    "translate": "Translate this into {language}. Output ONLY the translation.",
    "fix": "Fix spelling, grammar and punctuation. Keep the meaning, language and tone. Output ONLY the corrected text.",
    "explain": "Explain this in simple words a beginner understands. Keep the same language as the text.",
    "reply": "Write a good reply to this message. Tone: {style}. Same language as the message. Output ONLY the reply.",
    "rewrite": "Rewrite this clearly and professionally. Tone: {style}. Same language. Output ONLY the rewritten text.",
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        import pyperclip
    except Exception:
        return "The clipboard library is missing. Run: pip install pyperclip"
    try:
        action = (parameters.get("action") or "read").lower()
        text = (pyperclip.paste() or "").strip()
        if not text:
            return "The clipboard is empty — copy some text first with Ctrl+C."
        if action == "read":
            return f"Clipboard ({len(text)} characters): {text[:600]}"
        if action not in _PROMPTS:
            return f"Unknown clipboard action '{action}'."
        from core import gemini
        instr = _PROMPTS[action].format(
            language=parameters.get("language") or "English",
            style=parameters.get("style") or "natural and polite",
        )
        out = gemini.text(f"{instr}\n\n---\n{text[:8000]}\n---", tier=gemini.FAST, timeout_ms=40_000)
        out = (out or "").strip()
        if not out:
            return "The model gave no answer — try again in a moment."
        if action != "summarize" and action != "explain":
            pyperclip.copy(out)
            tail = " It is on your clipboard now — just paste."
        else:
            tail = ""
        if player:
            try:
                player.show_content(action.upper(), out)
            except Exception:
                pass
        return out[:1500] + tail
    except Exception as e:
        return f"Clipboard AI failed: {e}"
