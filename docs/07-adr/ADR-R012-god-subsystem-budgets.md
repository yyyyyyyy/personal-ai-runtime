# ADR-R012 — God façade + subsystem LOC budgets (G2)

| Field | Content |
|-------|---------|
| Decision | 保留 Kernel/Brain/MCPHub façade `god_object_max_loc`；另对 `query_builder` / `sovereignty_ops` / `builtin_registration` 锁定文件清单与分项预算 |
| Context | 仅拆文件会逃避 God 度量；尽调要求诚实化 |
| Evidence | `check_concept_growth.SUBSYSTEM_LOC_*` |
| Consequences + | 复杂度外溢可见 |
| Consequences − | 抬预算需改脚本 + docs §4.4 |
| Still valid? | Yes |
