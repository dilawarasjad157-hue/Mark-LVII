"""Skip to the next/previous video or track, or auto-skip on a timer."""
import threading
import time

PLUGIN = {
    "name": "video_skip",
    "description": (
        "Control video/music playback in whatever player or browser tab is in front: "
        "next, previous, play/pause, or auto-skip every N seconds until told to stop. "
        "Use for 'next video', 'skip this', 'is video ko skip karo', 'har 30 second baad "
        "skip karte raho', 'auto skip band karo'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "next | previous | playpause | auto_skip_start | auto_skip_stop"},
            "every_seconds": {"type": "NUMBER",
                              "description": "For auto_skip_start: seconds between skips (default 30)"},
            "count": {"type": "NUMBER", "description": "How many times to skip now (default 1)"},
        },
        "required": ["action"],
    },
}

_stop = threading.Event()
_thread = None


def _key(name: str):
    import pyautogui
    pyautogui.press(name)


def _loop(every: float):
    while not _stop.wait(every):
        try:
            _key("nexttrack")
        except Exception:
            pass


def run(parameters: dict, player=None, session_memory=None) -> str:
    global _thread
    try:
        action = (parameters.get("action") or "next").lower()
        if action in ("next", "skip"):
            n = max(1, int(parameters.get("count") or 1))
            for _ in range(n):
                _key("nexttrack")
                time.sleep(0.4)
            return "Skipped to the next one." if n == 1 else f"Skipped {n} times."
        if action in ("previous", "prev", "back"):
            _key("prevtrack")
            return "Went back."
        if action in ("playpause", "pause", "play"):
            _key("playpause")
            return "Toggled play and pause."
        if action == "auto_skip_start":
            every = max(3.0, float(parameters.get("every_seconds") or 30))
            _stop.set()
            time.sleep(0.05)
            _stop.clear()
            _thread = threading.Thread(target=_loop, args=(every,), daemon=True)
            _thread.start()
            return f"Auto-skip on, every {int(every)} seconds. Say stop to end it."
        if action == "auto_skip_stop":
            _stop.set()
            return "Auto-skip stopped."
        return "I did not understand that skip action."
    except Exception as e:
        return f"Video skip failed: {e}"
