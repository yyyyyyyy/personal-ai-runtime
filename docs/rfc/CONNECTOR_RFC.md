# Connector · RFC v0.1

> 连接器验收标准：**捕获自我的一个维度**，而非「给 AI 工具」。  
> 状态：**v0.1 — Ratified（calendar read-only）**  
> 实现：`backend/app/core/connectors/calendar_capture.py`

---

## §1 — 原则

1. Inbound only 写入 `ObservationRecorded`（或等价 Experience 事件）  
2. **禁止**连接器路径触发 Meaning 向上生成（`verify_meaning_dag` 必须通过）  
3. `actor=connector:*` 区分世界捕获与 user/system 行为  
4. 不经过 `TrajectoryLinked` 自动织线（须独立 suggester 提议）

## §2 — 首连接器：Calendar Read-Only

- 读取本地 ICS（`CalendarServer`）  
- 每条事件 → `ObservationRecorded` / `aggregate_type=observation`  
- payload: `{ source, calendar, title, file, captured_at }`

## §3 — API / 调度

v0.1：脚本与测试调用 `capture_calendar_observations(kernel)`；  
v0.2：scheduler 每日 ingest + UI 连接器状态。

## §4 — 验收

`backend/scripts/verify_connector.py` + CI

---

*See also: [`MEANING_ONTOLOGY.md`](MEANING_ONTOLOGY.md), [`TRAJECTORY_RFC.md`](TRAJECTORY_RFC.md).*
