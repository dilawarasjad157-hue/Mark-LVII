"""Is the internet healthy? Latency, download speed and public IP."""
import socket
import time

PLUGIN = {
    "name": "net_check",
    "description": (
        "Test the internet connection: ping/latency, download speed and public IP. "
        "Use for 'internet slow hai', 'net chal raha hai?', 'speed test karo', "
        "'mera IP kya hai', 'internet check karo'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "speed": {"type": "BOOLEAN", "description": "Also measure download speed (about 5 MB, default true)"},
        },
        "required": [],
    },
}


def _latency(host: str, port: int = 443) -> float | None:
    best = None
    for _ in range(3):
        t = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=3):
                ms = (time.perf_counter() - t) * 1000
                best = ms if best is None else min(best, ms)
        except OSError:
            continue
    return best


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        import requests
        ping = _latency("1.1.1.1")
        if ping is None:
            ping = _latency("8.8.8.8")
        if ping is None:
            return "There is no internet connection — I could not reach any server."
        parts = [f"Internet is up. Latency {ping:.0f} ms."]
        try:
            ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
            parts.append(f"Public IP {ip}.")
        except Exception:
            pass
        if parameters.get("speed", True) is not False:
            try:
                t = time.perf_counter()
                r = requests.get("https://speed.cloudflare.com/__down?bytes=5000000", timeout=15)
                secs = max(time.perf_counter() - t, 0.001)
                mbps = len(r.content) * 8 / secs / 1e6
                parts.append(f"Download about {mbps:.1f} Mbps.")
            except Exception:
                parts.append("Speed test could not finish.")
        verdict = "good" if ping < 80 else "slow" if ping < 200 else "poor"
        parts.append(f"Connection quality: {verdict}.")
        return " ".join(parts)
    except Exception as e:
        return f"Network check failed: {e}"
