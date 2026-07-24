# ADR-R013 — Knowledge Path B+ (decision gate)

| Field | Content |
|-------|---------|
| Decision | **保持 Path B**：Knowledge 为 non-sovereign attachment；加强 INV-S4 与 export 文案；**不**在本轮事件溯源化 |
| Context | 核实：`/api/system/export` 仅 snapshot/event_log；`NON_SOVEREIGN_ATTACHMENTS`；verify_export_roundtrip 不含 knowledge。产品未承诺「全部个人数据可从 export 重建含文档」 |
| Evidence | `table_registry.py`, `product/knowledge.py`, `api/system.py` docstring |
| Consequences + | 避免大文档进 event_log |
| Consequences − | 完整主权备份需另备 Knowledge 文件 |
| Still valid? | Conditional — 若产品承诺完整可重建则 revisit Path A |
