## 变更类型

- [ ] Bug 修复
- [ ] 新功能
- [ ] 重构（无功能变更）
- [ ] 概念删除 / 合并（减少了模块/事件/Fragment 数）

---

## Runtime Algebra 审查

见 [docs/02-concepts/runtime-algebra.md](docs/02-concepts/runtime-algebra.md)。

### 概念影响

- [ ] 本 PR 新增了**模块**（.py 文件）？ → 必须同时**删除**一个旧模块。
- [ ] 本 PR 新增了**事件类型**（`constants.py` 的 `EVENT_*`）？ → 被替换的是哪个旧事件类型？
- [ ] 本 PR 新增了**Fragment**？ → 被合并/删除的是哪个旧 Fragment？
- [ ] 本 PR 新增了**投影表**？ → 是否可以用现有表表达？
- [ ] 本 PR 新增了**`query_state` selector**？ → 是否有等价 selector 被删除？

### 一年测试

- [ ] 新增的每一个概念：一年后还会以独立身份存在吗？
  - 不确定 → 标注 `// EXPERIMENTAL: review by 20xx-xx`
  - 一定不存在 → 标注 `// DEPRECATED: migrate to X by vx.x`

### 吞并测试

- [ ] 新增概念能否用现有五原语（Event / State / Capability / Work / Context）组合表达？
  - 能 → 写为声明/实例，不要加新模块
  - 不能 → 在 PR 描述中解释为什么五原语不够

---

## 概念数量变化

| 指标 | 变更前 | 变更后 | 净变化 |
|---|---|---|---|
| `core/runtime/` 文件数 | | | |
| `constants.py` 事件类型数 | | | |
| `query_state` selector 分支数 | | | |
| Fragment 注册数 | | | |
| Governed 投影表数 | | | |
| Projector 文件数 | | | |

> 运行 `python scripts/check_concept_growth.py --snapshot` 获取当前基线。

---

## 测试

- [ ] 已有测试全部通过
- [ ] 新增了必要的测试
- [ ] 运行了 `make verify` 全部通过

---

## 备注

<!-- 描述本 PR 的动机、设计要点、风险点 -->
