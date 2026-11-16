"""
actions/launch_program.py — open any program, game, file, folder or link.

For a game this means the .exe, a shortcut, or a store link such as
steam://rungameid/<id>. For editing it means the editor itself or the project
file (a .prproj opens in Premiere, a .mp4 in the default player, and so on).
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

_OS = platform.system()
_URL_SCHEMES = ("http://", "https://", "steam://", "com.epicgames.launcher://",
                "ms-settings:", "file://", "spotify:", "discord://")


def _is_url(t: str) -> bool:
    return t.lower().startswith(_URL_SCHEMES)


def launch_program(parameters: dict, player=None) -> str:
    p = parameters or {}
    target = str(p.get("target", "")).strip().strip('"')
    if not target:
        return "What should I open?"
    args = str(p.get("args", "")).strip()

    expanded = os.path.expandvars(os.path.expanduser(target))
    path = Path(expanded)
    try:
        if _is_url(target):
            return _open_default(target)

        if path.exists():
            if args and path.is_file():
                subprocess.Popen(f'"{path}" {args}', shell=True, cwd=str(path.parent),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return f"Started {path.name} with arguments."
            return _open_default(str(path))

        # A bare program name: notepad, vlc, code, blender ...
        found = shutil.which(target)
        if found:
            subprocess.Popen([found] + (args.split() if args else []),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return f"Started {target}."

        if _OS == "Windows":
            # Start-menu names and registered apps ("chrome", "steam", "excel").
            subprocess.Popen(f'start "" "{target}" {args}', shell=True)
            return (f"I asked Windows to start '{target}'. It did not find a file "
                    f"by that path, so tell me if it does not appear.")
        return f"I could not find '{target}' on this computer."
    except Exception as e:
        return f"Could not open '{target}': {e}"


def _open_default(target: str) -> str:
    if _OS == "Windows":
        os.startfile(target)  # type: ignore[attr-defined]
    elif _OS == "Darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    return f"Opened {target}."


TOOL = {
    "name": "launch_program",
    "description": (
        "Opens ANY program, game, file, folder or link on this computer by its "
        "full path, name or URL: a game's .exe or shortcut, a Steam or Epic "
        "link (steam://rungameid/<id>), a video editor or its project file, a "
        "document, a folder. Use it when the user wants to play a game or open "
        "an editing project, especially when open_app cannot find it. Say it "
        "is opening, not that it is open. Closing things is computer_control "
        "with action='close_app'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {"type": "STRING", "description": "Full path, program name or URL to open"},
            "args": {"type": "STRING", "description": "Command-line arguments (optional)"},
        },
        "required": ["target"],
    },
    "handler": launch_program,
}
