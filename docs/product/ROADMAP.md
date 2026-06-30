# Roadmap

> 当前版本：v0.1.0。Runtime 核心治理完成。核心产品域（对话、记忆、目标、收件箱、审批）已落地。

---

## Phase 1：Trust Moat（信任护城河）

**时间**：6 个月

**目标**：让用户感知到「这个 AI 真正懂我」。建立迁移动力。

**用户问题**：当前的 AI 产品中，长期记忆是不可感知的。用户不知道 AI 记住了什么，也无法确认或纠正。

**完成标准**：

- 新用户首次使用 5 分钟内，看到 AI 对自己形成了一个初始画像
- 使用一周后，用户能看到「AI 对你的理解随时间增长」的可视化
- 换模型后 30 秒内，AI 仍然认得用户（内置一键 Demo）
- 用户能看到 AI 记忆的来源追溯（从哪次对话来的）

**要做的事**：

- AI 画像页面（偏好、习惯、目标、关系网——带置信度和来源引用）
- 对话中的「我记得」标记（AI 引用旧记忆时展示来源）
- 信任报告（数据存储位置、AI 做了什么、哪些需审批）
- 跨模型连续性内置 Demo
- 用户可确认、纠正、删除任何记忆

**坚决不做**：

- 不做 SDK/API 开放
- 不做云同步
- 不做移动端 App
- 不做 Workflow 编辑器（注：Workflow 可视化编辑器已在代码中实现，属于提前进入 Phase 2 范围的例外）
- 不做任何不直接提升记忆感知的工作

---

## Phase 2：Reach（扩展触达）

**时间**：12 个月

**前置条件**：Phase 1 完成标准全部达标

**目标**：从 Power User 扩展到知识工作者。从单设备扩展到多设备。

**用户问题**：愿意使用但不想自己配 `.env`。需要在多台设备上使用。

**完成标准**：

- 无需配 `.env` 即可使用（预置默认 LLM）
- 多设备间记忆和状态同步（端到端加密）
- 移动端可访问（PWA）
- 场景模版覆盖 20+ 常见使用场景
- 与主流生产力工具集成（Google Calendar、Notion）

**要做的事**：

- Zero-config Onboarding（预置免费 LLM 后端，一键启动）
- Encrypted Sync（端到端加密的 Event Log 跨设备同步）
- Scene Templates（「管理邮件」「追踪目标」「自动化日报」等一键场景）
- Integrations Hub（Google Calendar OAuth、Notion API、Obsidian 双向同步）
- Mobile PWA（响应式优化 + Web Push API）

**坚决不做**：

- 不做云托管（Self-host 是信任基础）
- 不做 AI Marketplace
- 不做企业版

---

## Phase 3：Platform（平台演化）

**时间**：12-18 个月

**前置条件**：10 万+ 活跃用户

**目标**：成为 Personal AI 品类的定义者。建立生态。

**用户问题**：用户希望在不同应用中共享同一段 AI 关系。开发者希望在自己的应用中复用 Memory 和 Governance。

**完成标准**：

- 100 万+ 活跃用户
- 平台上有 1000+ 社区贡献的 Skills / Templates
- 被主流媒体和行业报告列为 Personal AI 品类的代表
- 形成「换 AI 不换关系」的行业共识

**要做的事**：

- Stable API + SDK（Python SDK、TypeScript SDK）
- Skills Marketplace（社区贡献的场景模版、MCP Server）
- AI Portrait API（允许第三方应用读取用户画像，经用户授权）
- Trust Certification（数据主权的认证体系）

**坚决不做**：

- 不做模型训练
- 不做模型托管
- 不追求 Agent 自主性最大化

---

## 不在 Roadmap 范围内

以下方向明确排除：

- 多用户 / 多租户
- 分布式 Runtime
- 通用 Agent PaaS
- 完整 PII 脱敏
- 全库事件溯源
- 追求 Agent 自主性最大化
