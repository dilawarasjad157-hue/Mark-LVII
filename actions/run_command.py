"""
actions/run_command.py — a terminal for the assistant.

The user gave the assistant full control of the laptop. Anything without a
dedicated tool (installing a program, killing a process, ffmpeg, git, a script,
a Windows setting) goes through here.

The command's output is returned, never thrown away, so the assistant reports
what really happened.
"""
from __future__ import annotations

import os
import platform
import subprocess
import threading
from pathlib import Path

_OS = platform.system()
_MAX_OUT = 4000


def _clip(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= _MAX_OUT:
        return text
    return text[:_MAX_OUT // 2] + "\n...[cut]...\n" + text[-_MAX_OUT // 2:]


def _argv(command: str, shell: str) -> tuple[object, bool]:
    """(what to pass to Popen, whether shell=True)."""
    shell = (shell or "").lower()
    if _OS == "Windows" and shell in ("powershell", "pwsh", "ps"):
        return ["powershell", "-NoProfile", "-Command", command], False
    return command, True


def run_command(parameters: dict, player=None) -> str:
    p = parameters or {}
    command = str(p.get("command", "")).strip()
    if not command:
        return "What command should I run?"

    cwd = str(p.get("cwd", "")).strip() or None
    if cwd:
        cwd = os.path.expandvars(os.path.expanduser(cwd))
        if not Path(cwd).is_dir():
            return f"The folder {cwd} does not exist, so I did not run anything."

    try:
        timeout = int(p.get("timeout_seconds") or 60)
    except (TypeError, ValueError):
        timeout = 60
    timeout = max(1, min(timeout, 600))

    background = str(p.get("background", "")).lower() in ("1", "true", "yes")
    argv, use_shell = _argv(command, p.get("shell", ""))

    if player:
        try:
            player.write_log(f"SYS: run — {command[:120]}")
        except Exception:
            pass

    try:
        if background:
            kwargs = {}
            if _OS == "Windows":
                kwargs["creationflags"] = 0x00000008 | 0x00000200  # detached | new group
            else:
                kwargs["start_new_session"] = True
            log_path = Path.home() / ".jarvis_background.log"
            log = open(log_path, "ab")
            proc = subprocess.Popen(argv, shell=use_shell, cwd=cwd, stdout=log,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    **kwargs)
            threading.Thread(target=lambda: (proc.wait(), log.close()),
                             daemon=True).start()
            return f"Started in the background (pid {proc.pid}). Output goes to {log_path}."

        done = subprocess.run(argv, shell=use_shell, cwd=cwd, capture_output=True,
                              text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              errors="replace")
        out = _clip((done.stdout or "") + (("\n" + done.stderr) if done.stderr else ""))
        if done.returncode == 0:
            return f"Finished (exit 0).\n{out}" if out else "Finished (exit 0), no output."
        return f"The command failed (exit {done.returncode}).\n{out}"
    except subprocess.TimeoutExpired:
        return (f"The command did not finish within {timeout}s and was stopped. "
                f"For long jobs, run it again with background=true.")
    except Exception as e:
        return f"Could not run the command: {e}"


TOOL = {
    "name": "run_command",
    "description": (
        "Runs a terminal command on this computer (cmd/PowerShell on Windows, "
        "bash elsewhere) and returns its output. The user has given you full "
        "control of the laptop, so use this for anything without a dedicated "
        "tool: installing or uninstalling programs, killing a process, ffmpeg "
        "or other video/audio conversion, git, running scripts, changing a "
        "system setting. Report the real output; never claim success if the "
        "exit code was not 0. For long jobs (more than a minute) set "
        "background=true. To open an app, game, file or link use "
        "launch_program instead."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING", "description": "The command line to run"},
            "cwd": {"type": "STRING", "description": "Folder to run it in (optional)"},
            "shell": {"type": "STRING", "description": "'powershell' to use PowerShell on Windows (optional)"},
            "timeout_seconds": {"type": "INTEGER", "description": "Stop after this many seconds (default 60, max 600)"},
            "background": {"type": "BOOLEAN", "description": "Start it and return at once instead of waiting"},
        },
        "required": ["command"],
    },
    "handler": run_command,
}
