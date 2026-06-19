# relay-guard

**你的中转站(API relay)真的在跑你付费的模型吗?**
一行命令验真。零依赖,你的 key 全程不出本机。

[English →](./README.md) · [网页版(免费深度核验)→](https://panshi.io/zh/relay-check)

---

API 中转站到处都是——便宜,但有些会偷偷把你付费的贵模型(Claude / GPT / Gemini)
换成便宜模型,赚差价。你要 `claude-sonnet-4-6`,它给你一个套了壳的廉价模型。
`relay-guard` 帮你查上游到底是不是真货。

## 快速开始

```bash
# 免安装,只需 Python 3
curl -O https://raw.githubusercontent.com/<org>/relay-guard/main/relay_check.py
python3 relay_check.py
```

或带参数:

```bash
python3 relay_check.py \
  --base-url https://你的中转站.com/v1 \
  --key sk-xxxx \
  --model claude-sonnet-4-6 \
  --claim claude
```

## 它怎么查

默认跑**本地鲁棒信号**——全部在你本机完成,什么都不上传:

| 信号 | 抓什么 |
|---|---|
| **logprob 能力** | Anthropic 和 Google 的原生 API 不返回 token logprobs。若中转站*声称* Claude/Gemini 却返回了 logprobs,上游几乎肯定是被换成的 OpenAI 兼容模型。 |
| **自报身份泄漏** | 直接问模型谁造的它。一个自称 "Claude" 却说"我是 DeepSeek-R1"的,自己就招了。 |
| **模型枚举** | 列出这个 key 实际能访问的模型。 |

这些信号**不真的跑真模型就伪造不了**,而且工具刻意保守:宁可返回 `UNCERTAIN`,
也绝不冤判一个真端点。

```
==========================================================
  ⚠️ MISMATCH_SUSPECTED  Mismatch suspected / 疑似不符·掺水嫌疑
     Verdict / 检测结论
==========================================================
  Claimed / 你标称   : anthropic
  Detected / 实测    : deepseek
  Note / 说明        : claimed anthropic but endpoint returned token logprobs …
```

## 免费本地 vs 深度核验

本地信号抓**懒惰**的掺水。但高级中转站能用 prompt 注入让廉价模型*假装*成 Claude
——本地风格检查可能被骗。要给这种情形一锤定音,需要**中转站无法伪造的加密级核验**:

```bash
python3 relay_check.py --deep ...   # 加 panshi.io 指纹 + 签名验真
```

| | 本地(本 CLI) | 深度核验([panshi.io](https://panshi.io/zh/relay-check)) |
|---|---|---|
| 隐私 | key 和回答都留本地 | 只上传回答,绝不上传 key |
| 抓懒惰掺水 | ✅ | ✅ |
| 抓 persona 伪装 | ⚠️ 部分 | ✅ 统计指纹 |
| 加密级模型证明 | ✗ | ✅ 无法伪造的签名往返 |
| 持续监控 | ✗ | ✅ |

深度引擎(统计指纹、签名往返)按设计跑在服务端——既防中转站研究它来规避,
也因为这部分由 [panshi.io](https://panshi.io/zh/relay-check) 作为服务持续维护。

## 用于 CI

`--json` 在 `MISMATCH_SUSPECTED` 时返回非零退出码,可在中转站开始掺水时让构建失败:

```yaml
- run: |
    python3 relay_check.py --json \
      --base-url "$RELAY_URL" --key "$RELAY_KEY" \
      --model claude-sonnet-4-6 --claim claude
```

详见 [`.github/workflows/relay-guard.example.yml`](.github/workflows/relay-guard.example.yml)。

## 诚实的边界

这是概率工具,**不是法律证据**。量化/蒸馏的劣化版、以及参考库外的模型可能无法判定。
`LIKELY_GENUINE` 只降低嫌疑,不是保证。事关重大时,请用加密级深度核验。

## 协议

MIT © 2026 [panshi.io](https://panshi.io)
