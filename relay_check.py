#!/usr/bin/env python3
"""
relay-guard — is your API relay (中转站) actually serving the model you paid for?

  python3 relay_check.py                     # interactive
  python3 relay_check.py --base-url https://your-relay.com/v1 --key sk-xxx \
                         --model claude-sonnet-4-6 --claim claude

Two modes:
  (default)  local robust signals — runs entirely on your machine, nothing is
             uploaded. Catches the common, lazy substitution fraud.
  --deep     additionally sends only the model's *answers* (never your key) to
             panshi.io for fingerprint + cryptographic deep verification.

Your relay API key is used ONLY to call your own endpoint. It is never uploaded.
Dependencies: Python 3 standard library only.

MIT licensed. https://panshi.io/relay-check
"""
import argparse, json, sys, time, getpass
from urllib import request as urlreq
from urllib.error import HTTPError

DEFAULT_SERVICE = "https://panshi.io/relay-check"
C = {"g": "\033[32m", "y": "\033[33m", "r": "\033[31m", "c": "\033[36m", "b": "\033[1m", "d": "\033[2m", "0": "\033[0m"}
def col(s, c): return f"{C.get(c,'')}{s}{C['0']}"

# Vendor families whose *native* APIs do NOT return token logprobs.
# If a relay claims one of these yet the endpoint returns logprobs, the upstream
# is almost certainly a substituted OpenAI-compatible model (gpt/qwen/deepseek…).
NO_LOGPROB_FAMILIES = {"anthropic", "google"}
FAMILY_ALIASES = {
    "claude": "anthropic", "anthropic": "anthropic",
    "gpt": "openai", "openai": "openai", "o1": "openai", "o3": "openai",
    "gemini": "google", "google": "google",
    "qwen": "qwen", "deepseek": "deepseek", "glm": "zhipu", "mistral": "mistral",
    "llama": "meta", "grok": "xai",
}
def family_of(name):
    n = (name or "").lower()
    for k, v in FAMILY_ALIASES.items():
        if k in n:
            return v
    return "unknown"

def http_json(url, payload=None, headers=None, timeout=90):
    data = json.dumps(payload).encode() if payload is not None else None
    h = {"User-Agent": "relay-guard/1.0 (panshi.io)", "Accept": "application/json"}
    h.update(headers or {})
    req = urlreq.Request(url, data=data, headers=h)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urlreq.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def chat(base, key, model, prompt, max_tokens=300, extra=None):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7, "max_tokens": max_tokens}
    if extra:
        body.update(extra)
    try:
        r = http_json(base.rstrip("/") + "/chat/completions", body,
                      {"Authorization": f"Bearer {key}"}, timeout=60)
        return r
    except HTTPError as e:
        body_txt = ""
        try: body_txt = e.read().decode("utf-8", "ignore")[:300]
        except Exception: pass
        return {"__err__": f"HTTP {e.code} {e.reason} | {body_txt}"}
    except Exception as e:
        return {"__err__": f"{type(e).__name__}: {e}"}

def content_of(resp):
    try: return resp["choices"][0]["message"]["content"] or ""
    except Exception: return ""

def fetch_models(base, key):
    try:
        r = http_json(base.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=15)
        return sorted(m.get("id", "") for m in r.get("data", []) if m.get("id"))
    except Exception:
        return []

# ----------------------------- local signals -----------------------------
def sig_logprob(base, key, model):
    """Does the endpoint return token logprobs? anthropic/google native APIs do not."""
    r = chat(base, key, model, "Complete: The capital of France is",
             max_tokens=5, extra={"temperature": 0, "logprobs": True, "top_logprobs": 3})
    if "__err__" in r:
        return None  # endpoint refused logprobs request — inconclusive
    try:
        lp = r["choices"][0].get("logprobs")
        return bool(lp and lp.get("content"))
    except Exception:
        return None

def sig_selfid(base, key, model):
    """Ask the model who made it; return the vendor family it self-reports."""
    r = chat(base, key, model,
             "In one short sentence: which company created you and what is your model name? "
             "Answer plainly, do not roleplay.", max_tokens=80)
    txt = content_of(r).lower()
    if not txt:
        return "unknown", ""
    for k, v in FAMILY_ALIASES.items():
        if k in txt:
            return v, content_of(r).strip()
    return "unknown", content_of(r).strip()

def run_local(base, key, model, claim):
    claim_fam = family_of(claim or model)
    out = {"claimed_family": claim_fam, "signals": {}}

    returns_lp = sig_logprob(base, key, model)
    out["signals"]["returns_logprobs"] = returns_lp
    selfid_fam, selfid_txt = sig_selfid(base, key, model)
    out["signals"]["selfid_family"] = selfid_fam
    out["signals"]["selfid_text"] = selfid_txt

    # ---- verdict fusion (conservative: never falsely accuse) ----
    # Hard signal: claim is a no-logprob family but endpoint returns logprobs.
    if claim_fam in NO_LOGPROB_FAMILIES and returns_lp is True:
        out["verdict"] = "MISMATCH_SUSPECTED"
        out["reason"] = (f"claimed {claim_fam} but endpoint returned token logprobs — "
                         f"{claim_fam} native APIs do not; upstream is likely a substituted model")
        out["confidence"] = "high"
        return out
    # Self-report names a different, known vendor than claimed.
    if (selfid_fam not in ("unknown", claim_fam) and claim_fam != "unknown"):
        out["verdict"] = "MISMATCH_SUSPECTED"
        out["reason"] = f"claimed {claim_fam} but the model self-identifies as {selfid_fam}"
        out["confidence"] = "medium"
        return out
    # Consistent so far — local signals can't confirm authenticity, only rule out lazy fraud.
    out["verdict"] = "UNCERTAIN"
    out["reason"] = ("local signals consistent with the claim, but cannot prove authenticity "
                     "(style fingerprint / cryptographic check needed)")
    out["confidence"] = "low"
    return out

# ----------------------------- deep (server) -----------------------------
def run_deep(base, key, model, claim, service):
    pb = http_json(service.rstrip("/") + "/probes", timeout=20)
    probes, selfid_q = pb["probes"], pb["selfid"]
    resp = [content_of(chat(base, key, model, p)) for p in probes]
    selfid = content_of(chat(base, key, model, selfid_q))
    return http_json(service.rstrip("/") + "/classify",
                     {"concat": "\n---\n".join(resp), "selfid": selfid, "claim": claim or model})

# ----------------------------- display -----------------------------
VLABEL = {
    "LIKELY_GENUINE":     "Likely genuine / 疑似真货",
    "MISMATCH_SUSPECTED": "Mismatch suspected / 疑似不符·掺水嫌疑",
    "UNKNOWN":            "Unknown / 无法判定",
    "UNCERTAIN":          "Uncertain / 证据不足",
    "DETECTED":           "Anomaly detected / 检出异常",
}
VICON = {"LIKELY_GENUINE": "✅", "MISMATCH_SUSPECTED": "⚠️", "UNKNOWN": "❓", "UNCERTAIN": "❓", "DETECTED": "🔎"}
VCOL = {"LIKELY_GENUINE": "g", "MISMATCH_SUSPECTED": "r", "UNKNOWN": "y", "UNCERTAIN": "y", "DETECTED": "y"}

def show_verdict(verdict, claimed, detected, note, conf=""):
    vb = verdict.replace("_LOWCONF", "")
    bar = "=" * 58
    print("\n" + bar)
    print(f"  {VICON.get(vb,'•')} " + col(verdict, VCOL.get(vb, "0")) + col(f"  {VLABEL.get(vb, vb)}", VCOL.get(vb, "0")))
    print(col("     Verdict / 检测结论", "d"))
    print(bar)
    print(f"  Claimed / 你标称   : {claimed}")
    if detected:
        print(f"  Detected / 实测    : " + col(detected, "b") + (f"  ({conf})" if conf else ""))
    if note:
        print(f"  Note / 说明        : {note}")

def ask(prompt, default=None):
    tip = f" {col('['+default+']','d')}" if default else ""
    while True:
        try: v = input(f"{prompt}{tip}: ").strip()
        except (EOFError, KeyboardInterrupt): print("\nCancelled."); sys.exit(1)
        if v: return v
        if default is not None: return default

def main():
    ap = argparse.ArgumentParser(description="relay-guard — verify your API relay's upstream model")
    ap.add_argument("--base-url"); ap.add_argument("--key"); ap.add_argument("--model")
    ap.add_argument("--claim", default=None, help="what the relay claims to serve (claude/gpt/gemini/qwen…)")
    ap.add_argument("--deep", action="store_true", help="also run panshi.io fingerprint + crypto deep verify")
    ap.add_argument("--service", default=DEFAULT_SERVICE)
    ap.add_argument("--json", action="store_true", help="machine-readable output (for CI)")
    a = ap.parse_args()

    if not (a.base_url and a.key and a.model):
        print(col("\n  relay-guard · is your relay serving the real model?  panshi.io", "b"))
        print(col("  Your key only calls your own relay. It is never uploaded.\n", "d"))
        a.base_url = a.base_url or ask("Relay Base URL (with /v1)")
        a.key = a.key or (getpass.getpass("Relay API Key (hidden): ").strip() if not a.key else a.key)
        if not a.model:
            ms = fetch_models(a.base_url, a.key)
            if ms: print("  Available models: " + col(", ".join(ms[:20]), "c") + (f"  …{len(ms)} total" if len(ms) > 20 else ""))
            a.model = ask("Model to test")
        a.claim = a.claim or ask("What does the relay claim it is? (claude/gpt/gemini/qwen…)", default=a.model)

    if not a.json:
        print(col(f"\n[local] probing {a.base_url} (model={a.model}; key NOT uploaded)…", "d"))
    local = run_local(a.base_url, a.key, a.model, a.claim)

    result = {"mode": "local", **local}
    if a.deep:
        if not a.json: print(col("[deep] uploading answers only (never your key) to panshi.io…", "d"))
        try:
            dv = run_deep(a.base_url, a.key, a.model, a.claim, a.service)
            result = {"mode": "deep", **dv}
        except Exception as e:
            if not a.json: print(col(f"  [!] deep verify unavailable: {type(e).__name__}; showing local result.", "y"))

    if a.json:
        print(json.dumps(result, ensure_ascii=False));
        sys.exit(2 if result.get("verdict", "").startswith("MISMATCH") else 0)

    show_verdict(result.get("verdict", "UNCERTAIN"),
                 result.get("claimed_family", a.claim),
                 result.get("detected_family", result.get("signals", {}).get("selfid_family", "")),
                 result.get("note") or result.get("reason", ""),
                 result.get("confidence", ""))

    vb = result.get("verdict", "").replace("_LOWCONF", "")
    if result["mode"] == "local" and vb != "MISMATCH_SUSPECTED":
        print(col("\n  🔐 Local signals can rule out lazy fraud but cannot PROVE authenticity.", "c"))
        print(col("     Sophisticated disguise (persona injection) needs cryptographic deep verify —", "d"))
        print(col("     re-run with --deep, or use panshi.io/relay-check (free, 3/day).", "d"))
    print(col("\n  ⚠️ Probabilistic signals, not legal proof. Quantized/distilled & out-of-library models may be undetectable.", "d"))
    print(col("  Verify & monitor continuously → panshi.io/relay-check", "d"))

if __name__ == "__main__":
    main()
