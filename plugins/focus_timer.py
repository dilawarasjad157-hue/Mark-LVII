"""Countdown timers and Pomodoro focus sessions that speak when they finish."""
import threading
import time

PLUGIN = {
    "name": "focus_timer",
    "description": (
        "Start a countdown timer or a Pomodoro focus session INSIDE JARVIS and be "
        "told when it ends. Use for 'timer lagao 10 minute ka', 'pomodoro shuru "
        "karo', '25 minute focus', 'break ka timer', 'timer kitna bacha hai', "
        "'timer cancel karo'. For a reminder at a clock time (e.g. 6 PM) use the "
        "reminder tool instead."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "start | pomodoro | status | cancel"},
            "minutes": {"type": "NUMBER", "description": "Length in minutes (start). Decimals allowed."},
            "label": {"type": "STRING", "description": "What it is for, e.g. 'tea' or 'study'"},
            "cycles": {"type": "INTEGER", "description": "Pomodoro: number of work blocks (default 4)"},
            "work_minutes": {"type": "NUMBER", "description": "Pomodoro work block (default 25)"},
            "break_minutes": {"type": "NUMBER", "description": "Pomodoro short break (default 5)"},
        },
        "required": ["action"],
    },
}

_timers: dict[int, dict] = {}
_next_id = 1
_lock = threading.Lock()


def _beep():
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1000, 180)
            time.sleep(0.08)
    except Exception:
        pass


def _announce(player, text: str):
    _beep()
    if not player:
        return
    try:
        player.write_log(f"SYS: {text}")
        player.show_content("TIMER", text)
    except Exception:
        pass
    try:   # makes the assistant say it out loud
        cb = player.on_text_command
        if cb:
            cb(f"[SYSTEM_ALERT] {text} Tell the user in one short sentence.")
    except Exception:
        pass


def _schedule(player, tid: int, steps: list[tuple[str, float]], i: int = 0):
    if i >= len(steps):
        with _lock:
            _timers.pop(tid, None)
        return
    label, seconds = steps[i]

    def fire():
        with _lock:
            if tid not in _timers:
                return
        nxt = steps[i + 1][0] if i + 1 < len(steps) else None
        _announce(player, f"{label} is over." + (f" Next: {nxt}." if nxt else " All done."))
        _schedule(player, tid, steps, i + 1)

    t = threading.Timer(seconds, fire)
    t.daemon = True
    with _lock:
        if tid not in _timers:
            return
        _timers[tid].update(timer=t, step=i, ends=time.time() + seconds, label=label)
    t.start()


def _start(player, steps: list[tuple[str, float]], name: str) -> str:
    global _next_id
    with _lock:
        tid = _next_id
        _next_id += 1
        _timers[tid] = {"name": name, "timer": None, "ends": 0, "label": name, "steps": len(steps)}
    _schedule(player, tid, steps)
    first = steps[0]
    return f"Started: {first[0]} for {first[1] / 60:g} minutes."


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = (parameters.get("action") or "start").lower()
        if action == "start":
            mins = float(parameters.get("minutes") or 0)
            if not 0 < mins <= 24 * 60:
                return "Tell me how many minutes — between one second and 24 hours."
            label = (parameters.get("label") or "Timer").strip()
            return _start(player, [(label, mins * 60)], label)
        if action == "pomodoro":
            work = float(parameters.get("work_minutes") or 25)
            brk = float(parameters.get("break_minutes") or 5)
            cycles = max(1, min(8, int(parameters.get("cycles") or 4)))
            steps = []
            for c in range(1, cycles + 1):
                steps.append((f"Focus block {c} of {cycles}", work * 60))
                if c < cycles:
                    steps.append((f"Break {c}", (15 if c % 4 == 0 else brk) * 60))
            return _start(player, steps, "Pomodoro") + f" {cycles} blocks in total."
        if action == "status":
            with _lock:
                live = [(t["label"], max(0, t["ends"] - time.time())) for t in _timers.values()]
            if not live:
                return "No timers are running."
            return "; ".join(f"{l}: {int(s // 60)} min {int(s % 60)} s left" for l, s in live)
        if action in ("cancel", "stop"):
            with _lock:
                n = len(_timers)
                for t in _timers.values():
                    if t.get("timer"):
                        t["timer"].cancel()
                _timers.clear()
            return f"Cancelled {n} timer(s)." if n else "No timers were running."
        return f"Unknown timer action '{action}'."
    except Exception as e:
        return f"Timer failed: {e}"
