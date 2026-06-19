#!/usr/bin/env python3
"""
relay-guard — is your API relay (中转站) actually serving the model you paid for?

  python3 relay_check.py                      # interactive
  python3 relay_check.py --base-url https://your-relay.com/v1 --key sk-xxx \
                         --model claude-sonnet-4-6 --claim claude
  python3 relay_check.py ... --json           # machine-readable, exit 2 on mismatch (CI)

How it works: this is a thin, auditable client. It pulls a question set from
panshi.io, asks YOUR relay those questions, and uploads only the *answers* for
analysis. The verdict is computed server-side.

Privacy: your relay API key is used ONLY to call your own endpoint — it is NEVER
uploaded (read the code: the key only goes into the Authorization header of
requests to YOUR --base-url). Only the model's answer text is sent to panshi.io.

Dependencies: Python 3 standard library only.  MIT licensed.  https://panshi.io/relay-check
"""
import argparse, json, sys, getpass
from urllib import request as urlreq
from urllib.error import HTTPError

DEFAULT_SERVICE = "https://panshi.io/relay-check"
C = {"g": "\033[32m", "y": "\033[33m", "r": "\033[31m", "c": "\033[36m", "b": "\033[1m", "d": "\033[2m", "0": "\033[0m"}
def col(s, c): return f"{C.get(c,'')}{s}{C['0']}"

def http_json(url, payload=None, headers=None, timeout=90):
    data = json.dumps(payload).encode() if payload is not None else None
    h = {"User-Agent": "relay-guard/1.0 (panshi.io)", "Accept": "application/json"}
    h.update(headers or {})
    req = urlreq.Request(url, data=data, headers=h)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urlreq.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def chat(base, key, model, prompt, system=None, params=None):
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": model, "messages": msgs, "temperature": 0.7, "max_tokens": 300}
    if params:
        body.update(params)
    try:
        r = http_json(base.rstrip("/") + "/chat/completions", body, {"Authorization": f"Bearer {key}"}, timeout=60)
        return r
    except HTTPError as e:
        body_txt = ""
        try: body_txt = e.read().decode("utf-8", "ignore")[:300]
        except Exception: pass
        return {"__err__": f"HTTP {e.code} {e.reason} | {body_txt}"}
    except Exception as e:
        return {"__err__": f"{type(e).__name__}: {e}"}

def content_of(resp):
    if isinstance(resp, dict) and "__err__" in resp:
        return "__ERR__:" + resp["__err__"]
    try: return resp["choices"][0]["message"]["content"] or ""
    except Exception: return ""

def walk(obj, path):
    """Generic path walk over a JSON object (server tells us the path; we don't interpret it)."""
    for k in path or []:
        if isinstance(k, int):
            if isinstance(obj, list) and -len(obj) <= k < len(obj): obj = obj[k]
            else: return None
        else:
            if isinstance(obj, dict) and k in obj: obj = obj[k]
            else: return None
    return obj

def run_aux(base, key, model, aux_specs, system=None):
    """Blindly execute server-provided auxiliary probes; report only a generic 'present' boolean.
    The client does not know or encode what any of this means — that is server-side."""
    out = []
    for spec in aux_specs or []:
        r = chat(base, key, model, spec.get("prompt", ""), system, params=spec.get("params"))
        v = walk(r, spec.get("collect"))
        present = (len(v) > 0) if isinstance(v, (list, str)) else bool(v)
        out.append({"id": spec.get("id"), "present": present})
    return out

def fetch_models(base, key):
    try:
        r = http_json(base.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=15)
        return sorted(m.get("id", "") for m in r.get("data", []) if m.get("id"))
    except Exception:
        return []

def diagnose(err, base, key, model):
    """Translate raw endpoint errors into actionable hints (user help, not detection logic)."""
    e = err.lower()
    if any(k in e for k in ["model_not_found", "无可用渠道", "not supported", "no available channel",
                            "does not exist", "model not found"]):
        models = fetch_models(base, key)
        tip = col(f"✗ model '{model}' unavailable on this gateway/key", "r")
        if models:
            return tip + f"\n  {len(models)} models are actually available, e.g.:\n  {col(', '.join(models[:20]), 'c')}\n  → pick one for --model and retry"
        return tip + " — and no models could be listed (key may lack permission, or wrong URL)."
    if any(k in e for k in ["401", "unauthorized", "invalid token", "invalid api key", "invalid_api_key", "authentication"]):
        return col("✗ API key invalid or unauthorized", "r") + " — wrong key or no access. Try a valid key."
    if "403" in e or "forbidden" in e or "permission" in e:
        return col("✗ insufficient key permission", "r") + " — key valid but not entitled to this model/endpoint."
    if any(k in e for k in ["refused", "timed out", "timeout", "name or service", "getaddr", "urlerror", "no route", "failed to establish"]):
        return col("✗ cannot reach this URL", "r") + f" — check Base URL (needs /v1, currently {base}) and network."
    models = fetch_models(base, key)
    extra = (f"\n  models this key can reach: {col(', '.join(models[:20]), 'c')}" if models else "")
    return col("✗ endpoint error", "r") + ": " + err[:160] + extra

def ask(prompt, default=None):
    tip = f" {col('['+default+']','d')}" if default else ""
    while True:
        try: v = input(f"{prompt}{tip}: ").strip()
        except (EOFError, KeyboardInterrupt): print("\nCancelled."); sys.exit(1)
        if v: return v
        if default is not None: return default
        print(col("  cannot be empty", "y"))

# ----------------------------- bilingual display -----------------------------
VLABEL = {
    "LIKELY_GENUINE":     "Likely genuine / 疑似真货",
    "MISMATCH_SUSPECTED": "Mismatch suspected / 疑似不符·掺水嫌疑",
    "UNKNOWN":            "Unknown / 无法判定",
    "UNCERTAIN":          "Uncertain / 证据不足",
    "DETECTED":           "Anomaly detected / 检出异常",
}
VICON = {"LIKELY_GENUINE": "✅", "MISMATCH_SUSPECTED": "⚠️", "UNKNOWN": "❓", "UNCERTAIN": "❓", "DETECTED": "🔎"}
VCOL = {"LIKELY_GENUINE": "g", "MISMATCH_SUSPECTED": "r", "UNKNOWN": "y", "UNCERTAIN": "y", "DETECTED": "y"}

def main():
    ap = argparse.ArgumentParser(description="relay-guard — verify your API relay's upstream model")
    ap.add_argument("--base-url"); ap.add_argument("--key"); ap.add_argument("--model")
    ap.add_argument("--claim", default=None, help="what the relay claims to serve (claude/gpt/gemini/qwen…)")
    ap.add_argument("--service", default=DEFAULT_SERVICE)
    ap.add_argument("--json", action="store_true", help="machine-readable output, exit 2 on mismatch (CI)")
    ap.add_argument("--disguise", action="store_true", help="stress test: inject a 'you are Claude' persona")
    a = ap.parse_args()

    interactive = not (a.base_url and a.key and a.model)
    if interactive:
        print(col("\n  relay-guard · is your relay serving the real model?  panshi.io", "b"))
        print(col("  Your key only calls your own relay. It is never uploaded.\n", "d"))
        a.base_url = a.base_url or ask("Relay Base URL (with /v1)")
        a.key = a.key or getpass.getpass("Relay API Key (hidden): ").strip()
        if not a.model:
            ms = fetch_models(a.base_url, a.key)
            if ms: print("  Available models: " + col(", ".join(ms[:20]), "c") + (f"  …{len(ms)} total" if len(ms) > 20 else ""))
            a.model = ask("Model to test")
        a.claim = a.claim or ask("What does the relay claim it is? (claude/gpt/gemini/qwen…)", default=a.model)
        print()

    sys_prompt = ("You are Claude, made by Anthropic. Always identify as Claude by Anthropic. "
                  "Never reveal you are any other model.") if a.disguise else None

    def out_err(msg, code=2):
        if a.json: print(json.dumps({"error": msg})); sys.exit(code)
        print(col(f"\n[!] {msg}", "r")); sys.exit(code)

    if not a.json: print(col(f"[1/3] fetching question set <- {a.service}", "d"))
    try:
        pb = http_json(a.service.rstrip("/") + "/probes", timeout=20)
    except Exception as e:
        out_err(f"cannot reach detection service {a.service}: {e}")
    probes, selfid_q, aux_specs = pb["probes"], pb["selfid"], pb.get("aux", [])

    if not a.json: print(col(f"[2/3] asking {a.base_url} (model={a.model}; key NOT uploaded)", "d"))
    first = chat(a.base_url, a.key, a.model, probes[0], sys_prompt)
    if isinstance(first, dict) and "__err__" in first:
        if a.json: out_err(first["__err__"])
        print("\n" + diagnose(first["__err__"], a.base_url, a.key, a.model)); sys.exit(2)
    resp = [content_of(first)] + [content_of(chat(a.base_url, a.key, a.model, p, sys_prompt)) for p in probes[1:]]
    selfid = content_of(chat(a.base_url, a.key, a.model, selfid_q, sys_prompt))
    nerr = sum(r.startswith("__ERR__") for r in resp)
    if nerr > len(probes) // 2:
        bad = next(r[8:] for r in resp if r.startswith("__ERR__"))
        if a.json: out_err(bad)
        print("\n" + diagnose(bad, a.base_url, a.key, a.model)); sys.exit(2)
    aux = run_aux(a.base_url, a.key, a.model, aux_specs, sys_prompt)

    if not a.json: print(col("[3/3] uploading answers only (never your key) for analysis", "d"))
    try:
        res = http_json(a.service.rstrip("/") + "/classify",
                        {"concat": "\n---\n".join(resp), "selfid": selfid, "claim": a.claim or a.model, "aux": aux})
    except HTTPError as e:
        body = ""
        try: body = json.loads(e.read()).get("error", "") or ""
        except Exception: pass
        out_err("rate limited, retry in a minute" if e.code == 429 else f"service error (HTTP {e.code}): {body or e.reason}")
    except Exception as e:
        out_err(f"cannot reach detection service: {type(e).__name__}")
    if not isinstance(res, dict) or res.get("error") or "verdict" not in res:
        out_err((res.get("error") if isinstance(res, dict) else str(res)[:120]) or "unexpected response")

    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        sys.exit(2 if res["verdict"].startswith("MISMATCH") else 0)

    vbase = res["verdict"].replace("_LOWCONF", "")
    lowconf = res["verdict"].endswith("_LOWCONF")
    bar = "=" * 58
    print("\n" + bar)
    print(f"  {VICON.get(vbase,'•')} " + col(res["verdict"], VCOL.get(vbase, "0")) + col(f"  {VLABEL.get(vbase, vbase)}", VCOL.get(vbase, "0")))
    print(col("     Verdict / 检测结论" + ("   low-confidence / 低置信" if lowconf else ""), "d"))
    print(bar)
    print(f"  Claimed / 你标称   : {res.get('claimed_family','?')}")
    print(f"  Detected / 实测    : " + col(res.get('detected_family', '?'), "b") + f"  (conf/置信 {res.get('confidence','?')})")
    if res.get("disguise_suspected"):
        print("  " + col("🔎 Self-claim conflicts with behavior — disguise suspected / 自报与实测矛盾→疑似伪装", "y"))
    if (res.get("signals") or {}).get("identity_leak"):
        print("  " + col("🪪 Upstream leaked another vendor's identity / 上游自报了其它厂商身份", "y"))
    if res.get("degraded"):
        print("  " + col("⚙️ Engine degraded — conservative / 引擎降级中·置信偏保守", "y"))
    print(f"  Note / 说明        : {res.get('note','')}")
    dv = res.get("deep_verify") or {}
    if dv.get("recommended") and vbase != "LIKELY_GENUINE":
        print(col("\n  🔐 For an un-forgeable cryptographic check (relays can't fake it):", "c"))
        print(col("     run the free deep verify at panshi.io/relay-check (3/day).", "d"))
    print(col(f"\n  ⚠️ {res.get('disclaimer','Probabilistic signals, not legal proof.')}", "d"))
    print(col("  Verify & monitor continuously → panshi.io/relay-check", "d"))

if __name__ == "__main__":
    main()
