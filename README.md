# relay-guard

**Is your API relay (中转站) actually serving the model you paid for?**
One command to find out. No dependencies, your key never leaves your machine.

[中文说明 →](./README.zh.md) · [Web version (free deep verify) →](https://panshi.io/relay-check)

---

API relay / proxy services are everywhere — they're cheap, but some quietly swap
the expensive model you paid for (Claude, GPT, Gemini) with a cheaper one and
pocket the difference. You ask for `claude-sonnet-4-6`; you get a budget model in
a trench coat. `relay-guard` checks whether your upstream is the real thing.

## Quick start

```bash
# no install — just Python 3
curl -O https://raw.githubusercontent.com/<org>/relay-guard/main/relay_check.py
python3 relay_check.py
```

Or non-interactive:

```bash
python3 relay_check.py \
  --base-url https://your-relay.com/v1 \
  --key sk-xxxx \
  --model claude-sonnet-4-6 \
  --claim claude
```

## What it does

By default it runs **local, robust signals** — entirely on your machine, nothing
is uploaded:

| Signal | What it catches |
|---|---|
| **logprob capability** | Anthropic & Google native APIs don't return token logprobs. If a relay *claims* Claude/Gemini but the endpoint hands back logprobs, the upstream is almost certainly a substituted OpenAI-compatible model. |
| **self-identity leak** | Ask the model who made it. A "Claude" that says *"I'm DeepSeek-R1"* just told on itself. |
| **model enumeration** | Lists what the key can actually reach. |

These signals are **hard to fake without actually serving the real model**, and
the tool is deliberately conservative: it returns `UNCERTAIN` rather than falsely
accusing a genuine endpoint.

```
==========================================================
  ⚠️ MISMATCH_SUSPECTED  Mismatch suspected / 疑似不符·掺水嫌疑
     Verdict / 检测结论
==========================================================
  Claimed / 你标称   : anthropic
  Detected / 实测    : deepseek
  Note / 说明        : claimed anthropic but endpoint returned token logprobs …
```

## Free local vs. deep verification

Local signals catch the **lazy** fraud. A sophisticated relay can prompt-inject a
cheap model to *act* like Claude — local style checks can be fooled. To settle
those cases you need a **cryptographic check the relay cannot forge**:

```bash
python3 relay_check.py --deep ...   # adds panshi.io fingerprint + signature verify
```

| | Local (this CLI) | Deep verify ([panshi.io](https://panshi.io/relay-check)) |
|---|---|---|
| Privacy | key & answers stay local | only answers uploaded, never your key |
| Catches lazy substitution | ✅ | ✅ |
| Catches persona-injection disguise | ⚠️ partial | ✅ statistical fingerprint |
| Cryptographic proof of model | ✗ | ✅ un-forgeable signature round-trip |
| Continuous monitoring | ✗ | ✅ |

The deep engine (statistical fingerprints, signature round-trip) runs server-side
by design — both so relays can't study it to evade, and because that's the part
[panshi.io](https://panshi.io/relay-check) maintains as a service.

## Use in CI

`--json` exits non-zero on `MISMATCH_SUSPECTED`, so you can fail a build when your
relay starts cheating:

```yaml
- run: |
    python3 relay_check.py --json \
      --base-url "$RELAY_URL" --key "$RELAY_KEY" \
      --model claude-sonnet-4-6 --claim claude
```

See [`.github/workflows/relay-guard.example.yml`](.github/workflows/relay-guard.example.yml).

## Honest limits

This is a probabilistic tool, **not legal proof**. Quantized / distilled
degraded variants and models outside the reference library may be undetectable.
A `LIKELY_GENUINE` reduces suspicion; it is not a guarantee. When the stakes are
high, use the cryptographic deep verify.

## License

MIT © 2026 [panshi.io](https://panshi.io)
