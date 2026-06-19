# relay-guard

**你的中转站(API relay)真的在跑你付费的模型吗?**
一行命令验真。零依赖。**你的 key 全程不出本机。**

[English →](./README.md) · [网页版 →](https://panshi.io/zh/relay-check)

---

API 中转站到处都是——便宜,但有些会偷偷把你付费的贵模型(Claude / GPT / Gemini)
换成便宜模型赚差价。你要 `claude-sonnet-4-6`,它给你一个套了壳的廉价模型。
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

```
==========================================================
  ⚠️ MISMATCH_SUSPECTED  Mismatch suspected / 疑似不符·掺水嫌疑
     Verdict / 检测结论
==========================================================
  Claimed / 你标称   : anthropic
  Detected / 实测    : non-official-backend
  Note / 说明        : 端点特征与真 Claude 后端不符 …
```

## 工作原理(以及为什么可信)

这是一个**可审计的瘦客户端**——整个工具就是一个你能从头读到尾的 Python 文件:

1. 它从 panshi.io 拉一组题目;
2. 它拿这些题问**你自己的**中转站;
3. 它只把**回答**上传给 panshi.io,由服务端返回判定结论。

**你的中转站 key 绝不上传。** 读代码就知道:key 只会进到请求*你自己* `--base-url`
的 `Authorization` 头里,别的地方都碰不到你的 key。

检测引擎本身(怎么给回答打分)刻意跑在服务端——既防掺水中转站研究它来规避,
也因为这部分由 [panshi.io](https://panshi.io/zh/relay-check) 持续维护、随模型更新。

## 免费抽检 vs 持续监控

CLI(和[网页版](https://panshi.io/zh/relay-check))给你免费的按需**抽检**。但抽检只是
快照——中转站今天能过,明天就能换后端。要持续保护:

| | 本 CLI / 网页 | [panshi.io](https://panshi.io/zh/relay-check) 付费 |
|---|---|---|
| 按需检测 | ✅ 免费 | ✅ |
| 加密级深度核验(无法伪造) | 部分 | ✅ |
| 持续监控 + 告警 | ✗ | ✅ |
| 多上游看板 | ✗ | ✅ |

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

概率工具,**不是法律证据**。量化/蒸馏劣化版、参考集外的模型可能无法判定。
`LIKELY_GENUINE` 只降低嫌疑,不是保证。事关重大时请用加密级深度核验。

## 协议

MIT © 2026 [panshi.io](https://panshi.io)
