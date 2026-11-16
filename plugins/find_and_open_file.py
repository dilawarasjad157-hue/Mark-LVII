"""Find a file or folder by name in the usual places and open it."""
import os
import platform
import subprocess
from pathlib import Path

PLUGIN = {
    "name": "find_and_open_file",
    "description": (
        "Search the user's computer for a file or folder by (part of) its name and "
        "open it. Use when the user says 'find X and open it', 'open the file called X', "
        "'X file kholo / dhoondo'. Searches Desktop, Documents, Downloads, Pictures, "
        "Videos, Music and the home folder."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "Part of the file or folder name"},
            "extension": {"type": "STRING", "description": "Optional, like pdf, mp4, docx"},
        },
        "required": ["name"],
    },
}

_SKIP = {"appdata", "node_modules", ".git", "__pycache__", "site-packages", "windows"}


def _roots():
    home = Path.home()
    names = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"]
    roots = [home / n for n in names if (home / n).exists()]
    roots.append(home)
    return roots


def _search(query: str, ext: str, limit_dirs: int = 60000):
    q = query.lower()
    ext = ext.lower().lstrip(".")
    seen, hits, walked = set(), [], 0
    for root in _roots():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP and not d.startswith(".")]
            walked += 1
            if walked > limit_dirs:
                return hits
            for n in filenames + dirnames:
                if q in n.lower():
                    if ext and not n.lower().endswith("." + ext):
                        continue
                    full = os.path.join(dirpath, n)
                    if full not in seen:
                        seen.add(full)
                        hits.append(full)
            if len(hits) >= 20:
                return hits
    return hits


def _open(path: str):
    if platform.system() == "Windows":
        os.startfile(path)  # noqa
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        name = (parameters.get("name") or "").strip()
        if not name:
            return "Dilawar, which file should I look for?"
        hits = _search(name, parameters.get("extension") or "")
        if not hits:
            return f"I could not find anything named {name}."
        hits.sort(key=lambda p: (len(os.path.basename(p)), -os.path.getmtime(p)))
        best = hits[0]
        _open(best)
        msg = f"Opened {os.path.basename(best)}."
        if len(hits) > 1:
            msg += f" {len(hits) - 1} other matches exist."
        if player:
            try:
                player.write_log(f"JARVIS: {msg} ({best})")
            except Exception:
                pass
        return msg
    except Exception as e:
        return f"Find and open failed: {e}"
