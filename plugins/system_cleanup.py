"""Disk space report and safe temp-file cleanup."""
import os
import shutil
import tempfile
import time
from pathlib import Path

PLUGIN = {
    "name": "system_cleanup",
    "description": (
        "Check free disk space and clean junk temp files. Use for 'disk space "
        "kitni bachi hai', 'laptop slow hai safai karo', 'temp files delete karo', "
        "'junk clean karo', 'storage check'. action='disk' reports space, "
        "'scan' shows how much junk there is, 'clean' deletes temp files older "
        "than one day (never touches documents, downloads or anything in use)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "disk | scan | clean"},
            "older_than_hours": {"type": "NUMBER", "description": "Only files older than this (default 24)"},
        },
        "required": ["action"],
    },
}


def _roots() -> list[Path]:
    roots = {Path(tempfile.gettempdir())}
    if os.name == "nt":
        win = os.environ.get("SystemRoot")
        if win:
            roots.add(Path(win) / "Temp")
    return [r for r in roots if r.exists()]


def _walk(root: Path, min_age_s: float):
    now = time.time()
    for dp, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(dp, f)
            try:
                st = os.lstat(p)
                if now - st.st_mtime >= min_age_s:
                    yield p, st.st_size
            except OSError:
                continue


def _mb(n: float) -> str:
    if n < 1024 * 1024:
        return f"{n / 1024:,.0f} KB"
    return f"{n / 1024 / 1024:,.0f} MB" if n < 1024 ** 3 else f"{n / 1024 ** 3:,.1f} GB"


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = (parameters.get("action") or "disk").lower()
        age = float(parameters.get("older_than_hours") or 24) * 3600
        if action == "disk":
            anchor = os.path.abspath(os.sep) if os.name != "nt" else os.environ.get("SystemDrive", "C:") + "\\"
            u = shutil.disk_usage(anchor)
            return (f"Drive {anchor}: {_mb(u.free)} free of {_mb(u.total)} "
                    f"({u.used / u.total:.0%} used).")
        if action == "scan":
            total, count = 0, 0
            for r in _roots():
                for _p, sz in _walk(r, age):
                    total += sz
                    count += 1
            return f"{count} temp files older than {age / 3600:g} h, {_mb(total)} that can be cleared."
        if action == "clean":
            freed, removed = 0, 0
            for r in _roots():
                for p, sz in _walk(r, age):
                    try:
                        os.remove(p)
                        freed += sz
                        removed += 1
                    except OSError:
                        continue        # in use, or no permission: leave it
                for dp, dirs, files in os.walk(r, topdown=False):
                    for d in dirs:
                        try:
                            os.rmdir(os.path.join(dp, d))   # only if now empty
                        except OSError:
                            pass
            return f"Cleaned {removed} temp files and freed {_mb(freed)}. Files in use were skipped."
        return f"Unknown cleanup action '{action}'."
    except Exception as e:
        return f"Cleanup failed: {e}"
