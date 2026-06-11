# Egress · RFC v0.1

> LLM API 出站裁决与审计（宪法 §3 Data 边界第一刀）。  
> 状态：**v0.1 — Ratified（LLM only）** ｜ email/telegram 出站留待 v0.2  
> 实现：`backend/app/core/runtime/egress/egress_gate.py`

---

## §1 — 范围（v0.1）

**纳入：**

- Brain chat stream / continue  
- Review narrative LLM polish  
- 经 `prepare_llm_egress()` 包装的一切 LLM `messages` 出站

**不纳入（v0.2）：**

- `send_email` / `telegram_send` / `fetch_url` 等 MCP 工具出站

## §2 — Event Schema

```text
EgressApproved {
  purpose:      string   // chat_stream | review_narrative | ...
  classification: {
    categories: string[]  // identity_surface | memory_context | general
    message_count, char_count
  }
  redacted:     bool
}
```

`EgressDenied` 留待用户显式拒绝策略（v0.2）。

## §3 — 策略

1. **分类** — `classify_llm_payload()` 扫描 messages 合并文本  
2. **Redact** — `identity_surface` 命中时替换敏感 marker 为 `[redacted]`  
3. **审计** — 每次出站前 `emit_event(EgressApproved)`  
4. **默认允许** — v0.1 不阻断，仅 redact + audit（阻断策略 v0.2）

## §4 — 验收

`backend/scripts/verify_egress.py` + CI

---

*See also: [`HUMAN_RUNTIME_CONSTITUTION.md`](../HUMAN_RUNTIME_CONSTITUTION.md) §3, [`EPISTEMIC_CLOSURE_RFC.md`](EPISTEMIC_CLOSURE_RFC.md).*
