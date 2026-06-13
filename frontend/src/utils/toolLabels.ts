/** Human-readable labels and parameter descriptions for tool calls. */

interface ToolLabel {
  label: string;
  icon: string;
  /** Describe key arguments in plain Chinese, or a factory that builds a sentence from args. */
  describeArgs?: (args: Record<string, unknown>) => string;
}

// Internal map keyed by full tool name (builtin or mcp prefix).
// Falls back to common-sense patterns for unknown tools.
const TOOL_LABELS: Record<string, ToolLabel> = {
  // ── builtin ──
  get_current_time: { label: "获取当前时间", icon: "🕐" },
  read_file: {
    label: "读取文件",
    icon: "📄",
    describeArgs: (a) => `📂 ${a.path || "?"}`,
  },
  write_file: { label: "写入文件", icon: "✍️" },
  list_directory: { label: "列出目录内容", icon: "📁" },
  search_files: { label: "搜索文件", icon: "🔍" },
  web_search: {
    label: "搜索网页",
    icon: "🌐",
    describeArgs: (a) => `🔎 ${a.query || "?"}`,
  },
  fetch_url: {
    label: "抓取网页内容",
    icon: "📥",
    describeArgs: (a) => `🔗 ${a.url || "?"}`,
  },
  open_web_page: {
    label: "打开网页",
    icon: "🌍",
    describeArgs: (a) => `🔗 ${a.url || "?"}`,
  },
  search_and_extract: {
    label: "搜索并提取网页内容",
    icon: "🔎",
    describeArgs: (a) => `🔎 ${a.query || "?"}`,
  },
  list_calendar_events: { label: "查看日历日程", icon: "📅" },
  add_calendar_event: { label: "添加日历日程", icon: "📅" },
  get_upcoming_events: { label: "查看近期日程", icon: "📅" },
  check_inbox: { label: "检查收件箱", icon: "📧" },
  read_inbox_email: { label: "阅读邮件", icon: "📧" },
  send_email: { label: "发送邮件", icon: "✉️" },
  get_clipboard: { label: "读取剪贴板", icon: "📋" },
  ocr_image: { label: "图片文字识别", icon: "🔤" },
  shell_exec: {
    label: "执行命令",
    icon: "🖥️",
    describeArgs: (a) => `$ ${a.command || "?"}`,
  },
  git_status: { label: "查看 Git 状态", icon: "📊" },
  git_log: { label: "查看提交历史", icon: "📜" },
  git_diff: { label: "查看代码变更", icon: "📝" },
  telegram_send: { label: "发送 Telegram 消息", icon: "💬" },
  telegram_updates: { label: "查看 Telegram 消息", icon: "💬" },

  // ── MCP: playwright ──
  playwright_browser_navigate: {
    label: "打开网页",
    icon: "🌍",
    describeArgs: (a) => `🔗 ${a.url || "?"}`,
  },
  playwright_browser_snapshot: { label: "查看页面内容", icon: "👁️" },
  playwright_browser_take_screenshot: { label: "截取页面截图", icon: "📸" },
  playwright_browser_click: {
    label: "点击页面元素",
    icon: "👆",
    describeArgs: (a) => (a.element || a.target || a.selector || a.ref
      ? `点击 «${a.element || a.target || a.selector || a.ref}»`
      : "点击指定元素"),
  },
  playwright_browser_type: {
    label: "输入文字",
    icon: "⌨️",
    describeArgs: (a) => {
      const el = a.element || a.target || a.selector || a.ref || "目标";
      const txt = a.text || a.value || "…";
      return `在 «${el}» 输入 «${txt}»`;
    },
  },
  playwright_browser_tabs: { label: "管理浏览器标签页", icon: "📑" },
  playwright_browser_close: { label: "关闭浏览器", icon: "❌" },
  playwright_browser_fill_form: { label: "填写表单", icon: "📝" },
  playwright_browser_press_key: { label: "按下键盘按键", icon: "⌨️" },
  playwright_browser_select_option: { label: "选择下拉选项", icon: "📋" },
  playwright_browser_hover: { label: "鼠标悬停", icon: "🖱️" },
  playwright_browser_drag: { label: "拖拽元素", icon: "🖱️" },
  playwright_browser_evaluate: { label: "执行页面脚本", icon: "⚡" },
  playwright_browser_wait_for: { label: "等待页面加载", icon: "⏳" },
  playwright_browser_navigate_back: { label: "返回上一页", icon: "⬅️" },
  playwright_browser_resize: { label: "调整窗口大小", icon: "🪟" },
  playwright_browser_console_messages: { label: "查看控制台日志", icon: "📋" },
  playwright_browser_network_requests: { label: "查看网络请求", icon: "🌐" },

  // ── MCP: context7 ──
  context7_resolve_library_id: {
    label: "查询技术文档",
    icon: "📚",
    describeArgs: (a) => `📖 ${a.query || a.libraryId || a.library || a.lib || "?"}`,
  },
  context7_query_docs: {
    label: "查询技术文档",
    icon: "📚",
    describeArgs: (a) => `📖 ${a.query || a.libraryId || a.library || a.lib || "?"}`,
  },

  // ── MCP: brave ──
  brave_brave_web_search: {
    label: "搜索网页",
    icon: "🔍",
    describeArgs: (a) => `🔎 ${a.query || "?"}`,
  },

  // ── MCP: tavily ──
  tavily_tavily_search: {
    label: "深度搜索",
    icon: "🔬",
    describeArgs: (a) => `🔎 ${a.query || "?"}`,
  },
  tavily_tavily_extract: {
    label: "提取网页内容",
    icon: "📥",
    describeArgs: (a) => `🔗 ${a.url || "?"}`,
  },

  // ── MCP: github ──
  github_search_repositories: { label: "搜索仓库", icon: "📦", describeArgs: (a) => `🔎 ${a.query || "?"}` },
  github_search_code: { label: "搜索代码", icon: "🔍", describeArgs: (a) => `🔎 ${a.query || "?"}` },
  github_search_issues: { label: "搜索 Issue", icon: "🐛", describeArgs: (a) => `🔎 ${a.query || "?"}` },
  github_get_file_contents: { label: "查看文件内容", icon: "📄" },
  github_get_pull_request: { label: "查看 PR", icon: "🔀" },
  github_list_pull_requests: { label: "列出 PR", icon: "📋" },
  github_get_pull_request_files: { label: "查看 PR 变更文件", icon: "📂" },
  github_get_pull_request_status: { label: "查看 PR 状态", icon: "✅" },

  // ── MCP: notion ──
  notion_API_post_search: { label: "搜索文档", icon: "📄", describeArgs: (a) => `🔎 ${a.query || "?"}` },
  notion_API_retrieve_a_page: { label: "查看文档", icon: "📄" },
  notion_API_get_block_children: { label: "查看文章内容", icon: "📑" },
  notion_API_query_data_source: { label: "查询数据库", icon: "🗄️" },
};

/** Human-readable label for a tool name. Never exposes raw internal names. */
export function toolLabel(name: string): string {
  return TOOL_LABELS[name]?.label ?? fallbackLabel(name);
}

/** Icon emoji for a tool name. */
export function toolIcon(name: string): string {
  return TOOL_LABELS[name]?.icon ?? fallbackIcon(name);
}

/** Build a one-line Chinese sentence describing what the tool will do. */
export function describeToolAction(name: string, args: Record<string, unknown>): string {
  const entry = TOOL_LABELS[name];
  if (entry?.describeArgs) {
    return entry.describeArgs(args);
  }
  // Default: just show the label
  return entry?.label ?? fallbackLabel(name);
}

// ── fallbacks ──

function fallbackLabel(name: string): string {
  // Strip known prefixes
  const clean = name
    .replace(/^(playwright_|context7_|brave_|tavily_|github_|notion_)/, "")
    .replace(/_/g, " ")
    .replace(/\bAPI /g, "")
    .trim();
  const guess: Record<string, string> = {
    search: "搜索",
    navigate: "导航",
    click: "点击",
    type: "输入",
    read: "读取",
    write: "写入",
    get: "获取",
    list: "列出",
    create: "创建",
    update: "更新",
    delete: "删除",
    send: "发送",
    fetch: "抓取",
    query: "查询",
    resolve: "查询",
  };
  for (const [key, val] of Object.entries(guess)) {
    if (clean.toLowerCase().includes(key)) return val;
  }
  return clean || "执行操作";
}

function fallbackIcon(name: string): string {
  if (name.includes("search") || name.includes("query")) return "🔍";
  if (name.includes("navigate") || name.includes("web") || name.includes("page")) return "🌍";
  if (name.includes("click") || name.includes("hover")) return "👆";
  if (name.includes("type") || name.includes("input")) return "⌨️";
  if (name.includes("snapshot") || name.includes("screenshot")) return "📸";
  if (name.includes("read") || name.includes("get") || name.includes("list") || name.includes("retrieve")) return "📄";
  if (name.includes("write") || name.includes("create") || name.includes("send")) return "✍️";
  return "🔧";
}
