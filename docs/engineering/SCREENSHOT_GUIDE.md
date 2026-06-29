# README 截图资源

从运行中的前端（`http://localhost:5173`）抓取真实 UI 截图。

| 文件 | 页面 |
|------|------|
| `chat.png` | 对话首页 |
| `goals.png` | 目标管理 |
| `inbox.png` | 智能收件箱 |
| `dashboard.png` | 仪表盘 |
| `memories.png` | 记忆管理 |

## 重新生成

1. 启动应用：`make dev`（另开终端可先 `make demo` 写入示例数据）
2. 抓取截图：

```bash
make screenshots
```

脚本：`capture-screenshots.mjs`（Playwright）。脚本会自动设置 `localStorage.onboarding_done` 以跳过首次引导弹窗。修改前端 UI 后重新运行上述命令即可更新 PNG。
