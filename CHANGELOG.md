# Changelog

本文档记录 Personal AI Runtime 项目的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## [0.1.0] - 2026-06-29

### 变更

- **重置 Git 历史**：清除历史提交记录，以干净的状态开始

### 核心能力

- **Event Log**：append-only，不可改写
- **Deterministic Rebuild**：治理投影可确定性重建
- **Approval Governance**：高风险能力须用户确认
- **Capability Isolation**：CapabilityGateway + 污点追踪 + Fail-Closed 授权
- **对话 (Chat)**：带记忆和目标上下文的对话
- **收件箱 (Inbox)**：邮件轮询、分类、摘要
- **目标 (Goals)**：目标和行动管理，停滞检测与主动提醒
- **记忆 (Memories)**：长期记忆浏览、搜索、编辑
- **仪表盘 (Dashboard)**：系统状态概览

### 新增

- **AI 画像 (Portrait)**：聚合用户画像（偏好、价值观、关系、健康、财务、职业）、习惯、目标，含置信度评分与来源追溯 — `GET /api/memory/portrait`
- **对话「我记得」标记**：AI 引用记忆时在回复底部展示来源追溯（🧠 我记得），sources 从 SSE 瞬态改为持久化到 messages 表，刷新页面不丢失
- **信任报告 (Trust Report)**：展示数据存储位置、AI 活动摘要（LLM 调用/成本/工具统计）、待审批项概览，含流程上下文分类

---

[0.1.0]: https://github.com/yyyyyyyy/personal-ai-runtime/releases/tag/v0.1.0
