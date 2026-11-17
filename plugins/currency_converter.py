"""Live currency conversion — dollar, riyal, dirham, pound… to rupees and back."""
from datetime import datetime

PLUGIN = {
    "name": "currency_converter",
    "description": (
        "Convert money using TODAY's live exchange rate. Use for 'dollar ka rate', "
        "'100 dollar kitne rupay', 'how much is 50 euro in PKR', 'riyal to rupee', "
        "'dirham ka rate kya hai', 'pound aaj kitne ka hai'. Always use this instead "
        "of guessing a rate. Currencies can be names (dollar, rupee, riyal, dirham, "
        "pound, euro, yuan) or 3-letter codes (USD, PKR, SAR, AED)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "amount": {"type": "NUMBER", "description": "How much to convert (default 1)"},
            "from_currency": {"type": "STRING", "description": "Source currency, e.g. USD or dollar"},
            "to_currency": {"type": "STRING", "description": "Target currency (default PKR)"},
        },
        "required": ["from_currency"],
    },
}

_ALIASES = {
    "dollar": "USD", "dollars": "USD", "usd": "USD", "us dollar": "USD", "buck": "USD",
    "rupee": "PKR", "rupees": "PKR", "rupay": "PKR", "rupaye": "PKR", "rupya": "PKR",
    "pkr": "PKR", "pakistani rupee": "PKR",
    "inr": "INR", "indian rupee": "INR",
    "riyal": "SAR", "riyals": "SAR", "saudi riyal": "SAR", "sar": "SAR",
    "dirham": "AED", "dirhams": "AED", "aed": "AED",
    "pound": "GBP", "pounds": "GBP", "sterling": "GBP", "gbp": "GBP",
    "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "yuan": "CNY", "rmb": "CNY", "cny": "CNY",
    "yen": "JPY", "jpy": "JPY",
    "lira": "TRY", "try": "TRY",
    "ringgit": "MYR", "myr": "MYR",
    "taka": "BDT", "bdt": "BDT",
    "afghani": "AFN", "afn": "AFN",
    "canadian dollar": "CAD", "cad": "CAD",
    "australian dollar": "AUD", "aud": "AUD",
    "kuwaiti dinar": "KWD", "dinar": "KWD", "kwd": "KWD",
    "qatari riyal": "QAR", "qar": "QAR",
    "bitcoin": "BTC", "btc": "BTC",
}


def _code(name: str) -> str:
    n = (name or "").strip().lower()
    if n in _ALIASES:
        return _ALIASES[n]
    if len(n) == 3 and n.isalpha():
        return n.upper()
    return ""


def _rate(src: str, dst: str):
    """(rate, updated-text) from the first live source that answers."""
    import requests
    try:
        r = requests.get(f"https://open.er-api.com/v6/latest/{src}", timeout=8)
        j = r.json()
        if j.get("result") == "success" and dst in j.get("rates", {}):
            return float(j["rates"][dst]), (j.get("time_last_update_utc") or "")[:16]
    except Exception:
        pass
    try:
        r = requests.get(
            f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{src.lower()}.json",
            timeout=8)
        j = r.json()
        return float(j[src.lower()][dst.lower()]), j.get("date", "")
    except Exception:
        return None, ""


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        amount = float(parameters.get("amount") or 1)
        src = _code(parameters.get("from_currency", ""))
        dst = _code(parameters.get("to_currency") or "PKR")
        if not src or not dst:
            return "I could not tell which currencies you meant — please say them again."
        if src == dst:
            return f"{amount:g} {src} is {amount:g} {dst}."
        rate, when = _rate(src, dst)
        if rate is None:
            return "I could not reach a live exchange-rate service right now. Check the internet and try again."
        out = amount * rate
        stamp = when or datetime.now().strftime("%Y-%m-%d")
        text = (f"{amount:,.2f} {src} = {out:,.2f} {dst}. "
                f"Rate: 1 {src} = {rate:,.4f} {dst}, updated {stamp}.")
        if player:
            try:
                player.show_content("CURRENCY", text)
            except Exception:
                pass
        return text
    except Exception as e:
        return f"Currency conversion failed: {e}"
