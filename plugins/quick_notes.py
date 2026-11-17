"""Voice notes and a to-do list that survive restarts."""
import json
import threading
from datetime import datetime
from pathlib import Path

PLUGIN = {
    "name": "quick_notes",
    "description": (
        "Keep notes and a to-do list. Use for 'note kar lo ...', 'yaad rakhna ...', "
        "'mere notes dikhao', 'todo me add karo', 'meri task list', 'ye kaam ho gaya', "
        "'note delete karo', 'notes me search karo'. kind='note' for facts/ideas, "
        "kind='todo' for things to do. For a reminder at a SPECIFIC TIME use the "
        "reminder tool instead."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "add | list | search | done | delete | clear_done"},
            "kind": {"type": "STRING", "description": "note | todo (default note)"},
            "text": {"type": "STRING", "description": "Note text, search words, or the item to mark/delete"},
            "number": {"type": "INTEGER", "description": "Item number from the list, for done/delete"},
        },
        "required": ["action"],
    },
}

_FILE = Path(__file__).resolve().parent.parent / "memory" / "quick_notes.json"
_lock = threading.Lock()


def _load() -> list:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items: list) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_FILE)


def _fmt(items: list) -> str:
    rows = []
    for i, it in enumerate(items, 1):
        mark = "[x]" if it.get("done") else ("[ ]" if it["kind"] == "todo" else "-")
        rows.append(f"{i}. {mark} {it['text']}  ({it['created'][:10]})")
    return "\n".join(rows)


def _pick(items: list, number, text):
    if number:
        n = int(number) - 1
        return n if 0 <= n < len(items) else None
    t = (text or "").lower().strip()
    if not t:
        return None
    for i, it in enumerate(items):
        if t in it["text"].lower():
            return i
    return None


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = (parameters.get("action") or "list").lower()
        kind = "todo" if (parameters.get("kind") or "").lower().startswith("t") else "note"
        text = (parameters.get("text") or "").strip()
        number = parameters.get("number")
        with _lock:
            items = _load()
            if action == "add":
                if not text:
                    return "What should I write down?"
                items.append({"kind": kind, "text": text, "done": False,
                              "created": datetime.now().isoformat(timespec="seconds")})
                _save(items)
                return f"Saved {'to-do' if kind == 'todo' else 'note'} number {len(items)}: {text}"
            if action in ("list", "show"):
                view = [i for i in items if (not parameters.get("kind") or i["kind"] == kind)]
                if not view:
                    return "There is nothing saved yet."
                out = _fmt(view)
                if player:
                    try:
                        player.show_content("NOTES & TO-DO", out)
                    except Exception:
                        pass
                open_todos = sum(1 for i in view if i["kind"] == "todo" and not i.get("done"))
                return f"{len(view)} items, {open_todos} to-dos still open.\n{out}"
            if action == "search":
                hits = [i for i in items if text.lower() in i["text"].lower()]
                return _fmt(hits) if hits else f"Nothing matches '{text}'."
            if action in ("done", "complete", "finish"):
                idx = _pick(items, number, text)
                if idx is None:
                    return "I could not find that item. Say its number or a word from it."
                items[idx]["done"] = True
                _save(items)
                return f"Marked done: {items[idx]['text']}"
            if action in ("delete", "remove"):
                idx = _pick(items, number, text)
                if idx is None:
                    return "I could not find that item. Say its number or a word from it."
                gone = items.pop(idx)
                _save(items)
                return f"Deleted: {gone['text']}"
            if action == "clear_done":
                keep = [i for i in items if not i.get("done")]
                n = len(items) - len(keep)
                _save(keep)
                return f"Cleared {n} finished items."
            return f"Unknown notes action '{action}'."
    except Exception as e:
        return f"Notes failed: {e}"
