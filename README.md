# relay-guard

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE) ![Python 3](https://img.shields.io/badge/python-3.x-blue.svg) ![deps: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)

**Is your API relay (中转站) actually serving the model you paid for?**
One command to find out. Zero dependencies. **Your key never leaves your machine.**

[中文说明 →](./README.zh.md) · [Web version →](https://panshi.io/relay-check)

---

API relay / proxy services are everywhere — cheap, but some quietly swap the
expensive model you paid for (Claude, GPT, Gemini) with a cheaper one and pocket
the difference. You ask for `claude-sonnet-4-6`; you get a budget model in a
trench coat. `relay-guard` checks whether your upstream is the real thing.

## Quick start

```bash
# no install — just Python 3
curl -O https://raw.githubusercontent.com/akige/relay-guard/main/relay_check.py
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

```
==========================================================
  ⚠️ MISMATCH_SUSPECTED  Mismatch suspected / 疑似不符·掺水嫌疑
     Verdict / 检测结论
==========================================================
  Claimed / 你标称   : anthropic
  Detected / 实测    : non-official-backend
  Note / 说明        : endpoint behavior doesn't match a real Claude backend …
```

## How it works (and why you can trust it)

This is a **thin, auditable client** — the whole thing is one short Python file
you can read end to end:

1. It pulls a question set from panshi.io.
2. It asks **your** relay those questions.
3. It uploads only the **answers** to panshi.io, which returns a verdict.

**Your relay API key is never uploaded.** Read the code: the key only ever goes
into the `Authorization` header of requests to *your own* `--base-url`. Nothing
else touches your key.

The detection engine itself (how the answers are scored) runs server-side on
purpose — both so fraudulent relays can't study it to evade, and because that's
the part [panshi.io](https://panshi.io/relay-check) maintains and keeps current
as models change.

## Free vs. continuous

The CLI (and the [web version](https://panshi.io/relay-check)) give you a free,
on-demand **spot check**. But a spot check is a snapshot — a relay can pass today
and swap the backend tomorrow. For ongoing protection:

| | This CLI / web | [panshi.io](https://panshi.io/relay-check) paid |
|---|---|---|
| On-demand check | ✅ free | ✅ |
| Cryptographic deep verify (un-forgeable) | partial | ✅ |
| Continuous monitoring & alerts | ✗ | ✅ |
| Multi-upstream dashboard | ✗ | ✅ |

## Use in CI

`--json` exits non-zero on `MISMATCH_SUSPECTED`, so you can fail a build when
your relay starts cheating:

```yaml
- run: |
    python3 relay_check.py --json \
      --base-url "$RELAY_URL" --key "$RELAY_KEY" \
      --model claude-sonnet-4-6 --claim claude
```

See [`.github/workflows/relay-guard.example.yml`](.github/workflows/relay-guard.example.yml).

## Honest limits

A probabilistic tool, **not legal proof**. Quantized / distilled degraded
variants and models outside the reference set may be undetectable. A
`LIKELY_GENUINE` reduces suspicion; it is not a guarantee. For high-stakes cases,
use the cryptographic deep verify.

## License

MIT © 2026 [panshi.io](https://panshi.io)
