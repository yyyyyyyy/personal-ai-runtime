# 文档

按阅读目的组织，而不是按技术分类。

---

## 我想了解这个项目

| 文档 | 阅读时间 | 内容 |
|------|---------|------|
| **[WHY_NOW](product/WHY_NOW.md)** | 5 分钟 | 为什么是现在？AI 行业正在发生什么？ |
| **[MANIFESTO](product/MANIFESTO.md)** | 3 分钟 | 我们相信什么？拒绝什么？ |
| **[POSITIONING](product/POSITIONING.md)** | 5 分钟 | 产品定位与核心理念 |
| **[PRODUCT_STRATEGY](product/PRODUCT_STRATEGY.md)** | 15 分钟 | 目标市场、差异化战略、商业模式方向 |
| **[USER_STORIES](product/USER_STORIES.md)** | 5 分钟 | 谁在用？为什么离不开？ |

## 我想使用这个产品

| 文档 | 阅读时间 | 内容 |
|------|---------|------|
| **[USER_GUIDE](guides/USER_GUIDE.md)** | 10 分钟 | 安装、配置、日常使用 |
| **[API](reference/API.md)** | 5 分钟 | API 端点总览 + curl 示例 |
| **[CONFIGURATION](reference/CONFIGURATION.md)** | 3 分钟 | 环境变量和配置项说明 |

## 我想了解技术实现

| 文档 | 阅读时间 | 内容 |
|------|---------|------|
| **[ARCHITECTURE](architecture/ARCHITECTURE.md)** | 20 分钟 | 生产架构：分层、数据流、治理边界 |
| **[GOVERNANCE](architecture/GOVERNANCE.md)** | 8 分钟 | Context 编译层：Policy、Pipeline、Fragment 选择 |

## 我想参与开发

| 文档 | 阅读时间 | 内容 |
|------|---------|------|
| **[CONTRIBUTING](../CONTRIBUTING.md)** | 5 分钟 | 如何贡献 |
| **[DEVELOPER_GUIDE](guides/DEVELOPER_GUIDE.md)** | 15 分钟 | 添加 Tool、Fragment、Handler |
| **[PRINCIPLES](product/PRINCIPLES.md)** | 3 分钟 | 产品原则（决策框架） |

## 我想了解未来方向

| 文档 | 阅读时间 | 内容 |
|------|---------|------|
| **[ROADMAP](product/ROADMAP.md)** | 5 分钟 | Phase 1-3 路线 |

## 工程文档（内部）

以下文档面向核心维护者，不面向普通用户：

| 文档 | 内容 |
|------|------|
| **[NORTH_STAR](engineering/NORTH_STAR.md)** | 技术宪法（内部稿） |
| **[INVARIANTS](engineering/INVARIANTS.md)** | CI 守护的不可破坏规则 |
| **[CURRENT_STATE](engineering/CURRENT_STATE.md)** | 能力清单、成熟度评级 |
| **[HISTORY](engineering/HISTORY.md)** | 已完成里程碑 |
| **[SCREENSHOT_GUIDE](engineering/SCREENSHOT_GUIDE.md)** | 截图操作手册 |

---

## 阅读路径

### 第一次访问

```
README（30 秒）→ POSITIONING（5 分钟）→ USER_GUIDE（10 分钟）
```

### 投资人

```
WHY_NOW（5 分钟）→ PRODUCT_STRATEGY（15 分钟）→ MANIFESTO（3 分钟）→ ROADMAP（5 分钟）
```

### 开发者

```
README（2 分钟）→ DEVELOPER_GUIDE（15 分钟）→ ARCHITECTURE（20 分钟）
```

### 社区贡献者

```
README（2 分钟）→ CONTRIBUTING（5 分钟）→ DEVELOPER_GUIDE（15 分钟）
```

### API 集成者

```
README（2 分钟）→ API（5 分钟）→ CONFIGURATION（3 分钟）
```

### 企业评估者

```
WHY_NOW（5 分钟）→ PRODUCT_STRATEGY（15 分钟）→ ROADMAP（5 分钟）
```

---

## 文档维护

- **产品文档**（`product/`）：PM 维护，季度更新
- **使用指南**（`guides/`）：PM + 社区维护，重大功能发布时更新
- **架构文档**（`architecture/`）：核心开发者维护，架构变更时更新
- **参考文档**（`reference/`）：随代码变更更新
- **工程文档**（`engineering/`）：核心团队维护，里程碑后更新
