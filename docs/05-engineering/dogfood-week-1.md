# Dogfood Week 1 — 2026-07-13 至 2026-07-19

> 不是"用一下试试"，而是用真实使用压力测试 4 个核心子系统，并每天记录一次"卡点"。
> 这份日志本身就是下一轮重构的输入——参考 [runtime-algebra.md §5.4](../02-concepts/runtime-algebra.md) 的"开发期优先用 dogfood 证据驱动"。

## 起点状态（Day 0）

- 数据库现状：98 work_items（50 active goals / 36 pending tasks / 4 running / 8 completed）、14 conversations（多为 e2e 测试残留）、36 memories（30 fact + 4 event + 2 preference）
- 已知信号 1：**50 个 active goals 未流转** → 假设 A 验证起点
- 已知信号 2：**最近 5 个对话 0 msgs**（测试残留）→ 数据污染但保留观察
- 已知信号 3：**preference 记忆只有 2 条** → memory 提取可能漏偏好

## 每日最小动作（10 分钟）

1. 早 8:00 检查 `/dashboard` 看 morning_brief 是否触发、内容是否相关
2. 工作中遇到"想记的事" → 用 `/chat` 告诉它（测试 memory extraction）
3. 晚上花 5 分钟记一条："今天哪一步让我烦/卡住/看不懂"

## 重点验证的 4 个假设

| 假设 | 怎么验证 | 期望 |
|------|---------|------|
| A. WorkItem 生命周期在实际使用中卡住 | Day 3 看 50 active goals 是否减少；Day 7 看新创建目标能否正常 completed | 至少 30% 流转 |
| B. Memory 提取覆盖足够 | Day 7 看 Memories 页，统计"准确"vs"垃圾"比例 | 准确率 > 70% |
| C. Approval 治理不打扰 | 每天记录 approval 触发次数，标注哪些"问得多余" | 后期 < 3 次/天 |
| D. Morning Brief 有用 | 7 天里它真的帮你看清了当天 / 提醒了 deadline | 主观评分 ≥ 3/5 |

---

## Day 1 (2026-07-13)

### 用了哪些功能
- [ ] Chat
- [ ] Goals（创建/推进/完成）
- [ ] Inbox（poll/digest/分类）
- [ ] Calendar
- [ ] Knowledge（上传/检索）
- [ ] Morning Brief
- [ ] Memory（看 Memories 页）

### 今天的卡点（最重要的 1-3 条）
1.
2.
3.

### 触发的 Approval 次数 + 是否合理
- 共 N 次，其中 M 次觉得没必要问

### 响应速度感受
- 快 / 可接受 / 慢

---

## Day 2 (2026-07-14)

### 用了哪些功能
- [ ] Chat
- [ ] Goals
- [ ] Inbox
- [ ] Calendar
- [ ] Knowledge
- [ ] Morning Brief
- [ ] Memory

### 今天的卡点
1.
2.

### Approval 次数
-

### 响应速度
-

---

## Day 3 (2026-07-15) — 中期检查点

### 用了哪些功能
- [ ] Chat
- [ ] Goals
- [ ] Inbox
- [ ] Calendar
- [ ] Knowledge
- [ ] Morning Brief
- [ ] Memory

### 中期检查：50 个 active goals 现在多少？
- 数字：__ / 50（起点）
- 新创建：__
- 推进到 completed：__

### 今天的卡点
1.
2.

---

## Day 4 (2026-07-16)

### 用了哪些功能
- [ ] Chat
- [ ] Goals
- [ ] Inbox
- [ ] Calendar
- [ ] Knowledge
- [ ] Morning Brief
- [ ] Memory

### 今天的卡点
1.

### Approval 次数
-

---

## Day 5 (2026-07-17)

### 用了哪些功能
- [ ] Chat
- [ ] Goals
- [ ] Inbox
- [ ] Calendar
- [ ] Knowledge
- [ ] Morning Brief
- [ ] Memory

### 今天的卡点
1.

---

## Day 6 (2026-07-18)

### 用了哪些功能
- [ ] Chat
- [ ] Goals
- [ ] Inbox
- [ ] Calendar
- [ ] Knowledge
- [ ] Morning Brief
- [ ] Memory

### 今天的卡点
1.

---

## Day 7 (2026-07-19) — 最终检查

### Memories 页审视
- 总数：__
- 准确（应保留）：__
- 垃圾（应删除）：__
- 准确率：__%

### Approval 一周汇总
- 总次数：__
- 觉得"问得多余"的次数：__

### Morning Brief 一周评分
- 1 / 2 / 3 / 4 / 5

---

## Week 1 回顾（Day 8 填写）

### 1. 哪个子系统最阻碍日用？
（这是下一个重构 PR 的目标）

### 2. 哪个抽象"看起来重要但实际没用"？
（候选删除——通过 runtime-algebra.md §3.1 Subsumption Test）

### 3. 哪个功能"差一点就好用"？
（产品打磨优先级）

### 4. 数据污染（测试残留）是否真的影响了使用？
（验证"keep as is"的判断）

### 5. Review 里指出的债，哪些被 dogfood 证实是"真问题"？
- read_ports/ 拆分：证实 / 不重要
- API 三处混层：证实 / 不重要
- governance/ → context/ 重命名：证实 / 不重要
- test_coverage_*.py 清理：证实 / 不重要
- 其他：__

### 6. 下一周（Week 2）的方向
- [ ] 继续观察（数据还不够）
- [ ] 启动 P2 重构（基于本周证据）
- [ ] 启动未评审领域（async/SQLite、安全、frontend）
- [ ] 其他：__
