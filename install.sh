#!/usr/bin/env bash
# Personal AI Runtime — 一键安装脚本
# 用法: bash install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
DESKTOP_DIR="$ROOT/desktop"
ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── helpers ──────────────────────────────────────────────────────────

section()  { echo ""; echo -e "${BOLD}${CYAN}▶ $*${NC}"; }
success() { echo -e "  ${GREEN}✓${NC} $*"; }
warn()    { echo -e "  ${YELLOW}⚠${NC} $*"; }
fail()    { echo -e "  ${RED}✗${NC} $*"; exit 1; }

check_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少依赖: $1，请先安装后再运行本脚本"
}

# ── banner ───────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}Personal AI Runtime  安装脚本${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. 检查前置依赖 ──────────────────────────────────────────────────

section "1/5  检查前置依赖"

check_cmd python3
check_cmd node
check_cmd npm

PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$(python3 -c 'print(int(sys.version_info >= (3, 12)))')" != "1" ]; then
  fail "需要 Python >= 3.12，当前版本 $PYVER"
fi
success "Python $PYVER"

NODEVER=$(node -v | sed 's/^v//')
NODE_MAJOR=$(echo "$NODEVER" | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 20 ]; then
  fail "需要 Node.js >= 20，当前版本 $NODEVER"
fi
success "Node.js $NODEVER"
success "npm $(npm -v)"

# ── 2. 配置 .env ─────────────────────────────────────────────────────

section "2/5  配置环境变量"

if [ -f "$ENV_FILE" ]; then
  success "已存在 .env，跳过配置引导"
  if ! grep -q '^LLM_API_KEY=.*sk-' "$ENV_FILE" 2>/dev/null; then
    warn "注意: .env 中的 LLM_API_KEY 似乎不是有效的 API Key（应以 'sk-' 开头）"
    read -rp "  是否现在编辑 .env？[y/N] " edit_choice
    if [ "$edit_choice" = "y" ] || [ "$edit_choice" = "Y" ]; then
      cp "$ENV_FILE" "$ROOT/.env"
    fi
  fi
else
  echo "  未检测到 .env 文件，开始交互式配置..."
  echo ""

  cp "$ENV_EXAMPLE" "$ENV_FILE"

  # LLM Provider
  echo "  选择 LLM 提供商:"
  echo "    [1] DeepSeek (推荐，默认)"
  echo "    [2] OpenAI"
  echo "    [3] 自定义 OpenAI 兼容接口"
  read -rp "  请输入选择 [1-3，默认 1]: " provider_choice
  provider_choice="${provider_choice:-1}"

  case "$provider_choice" in
    2)
      read -rp "  OpenAI API Key (sk-...): " api_key
      if [ -n "$api_key" ]; then
        sed -i.bak "s|^LLM_API_KEY=.*|LLM_API_KEY=${api_key}|" "$ENV_FILE"
        sed -i.bak "s|^LLM_BASE_URL=.*|LLM_BASE_URL=https://api.openai.com/v1|" "$ENV_FILE"
        sed -i.bak "s|^LLM_MODEL=.*|LLM_MODEL=gpt-4o|" "$ENV_FILE"
      fi
      ;;
    3)
      read -rp "  API Base URL: " custom_url
      read -rp "  API Key: " custom_key
      read -rp "  Model Name: " custom_model
      [ -n "$custom_url" ] && sed -i.bak "s|^LLM_BASE_URL=.*|LLM_BASE_URL=${custom_url}|" "$ENV_FILE"
      [ -n "$custom_key" ] && sed -i.bak "s|^LLM_API_KEY=.*|LLM_API_KEY=${custom_key}|" "$ENV_FILE"
      [ -n "$custom_model" ] && sed -i.bak "s|^LLM_MODEL=.*|LLM_MODEL=${custom_model}|" "$ENV_FILE"
      ;;
    *)
      read -rp "  DeepSeek API Key (sk-...): " api_key
      if [ -n "$api_key" ]; then
        sed -i.bak "s|^LLM_API_KEY=.*|LLM_API_KEY=${api_key}|" "$ENV_FILE"
      fi
      ;;
  esac
  rm -f "$ENV_FILE.bak"

  # Email (optional)
  echo ""
  echo "  可选: 配置邮箱以启用收件箱功能"
  read -rp "  是否现在配置？[y/N] " email_choice
  if [ "$email_choice" = "y" ] || [ "$email_choice" = "Y" ]; then
    read -rp "  Gmail 地址: " email_user
    read -rp "  Gmail App Password (16位): " email_pass
    [ -n "$email_user" ] && sed -i.bak "s|^EMAIL_USER=.*|EMAIL_USER=${email_user}|" "$ENV_FILE"
    [ -n "$email_pass" ] && sed -i.bak "s|^EMAIL_PASS=.*|EMAIL_PASS=${email_pass}|" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
  fi

  success ".env 配置完成"
fi

# ── 3. 安装依赖 ──────────────────────────────────────────────────────

section "3/5  安装 Python 依赖"
cd "$BACKEND_DIR"
python3 scripts/check_dependency_sync.py
python3 -m pip install --require-hashes -r requirements.lock --quiet
success "Python 依赖安装完成"

section "3/5  安装前端依赖"
cd "$FRONTEND_DIR"
npm ci --silent 2>/dev/null || npm install --silent
success "前端依赖安装完成"

section "3/5  安装桌面端依赖"
cd "$DESKTOP_DIR"
if [ -f "package.json" ]; then
  npm ci --silent 2>/dev/null || npm install --silent
  success "桌面端依赖安装完成"
else
  warn "未找到 desktop/package.json，跳过桌面端依赖"
fi

cd "$ROOT"

# ── 4. 初始化数据库 ──────────────────────────────────────────────────

section "4/5  初始化数据库"

cd "$BACKEND_DIR"
if [ -f "alembic.ini" ]; then
  if python3 -m alembic upgrade head 2>/dev/null; then
    success "数据库初始化完成"
  else
    warn "alembic 迁移遇到问题（可能是首次运行），将在应用启动时自动初始化"
    warn "你可以在启动后观察日志确认 DB 是否正常创建"
  fi
else
  warn "未找到 alembic.ini，数据库将在首次启动时自动初始化"
fi
cd "$ROOT"

# ── 5. 验证安装 ──────────────────────────────────────────────────────

section "5/5  验证安装"

echo "  运行快速验证..."
cd "$BACKEND_DIR"

# Import check: can we import the main app?
if python3 -c "from app.main import app; print('OK')" 2>/dev/null; then
  success "应用导入测试通过"
else
  warn "应用导入测试未通过（但可能不影响运行，请检查 LLM_API_KEY 是否已配置）"
fi

cd "$ROOT"

# ── 完成 ─────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BOLD}${GREEN}  安装完成！${NC}"
echo ""
echo "  启动方式:"
echo ""
echo "    本地开发:  ${CYAN}make dev${NC}"
echo "    Docker:    ${CYAN}docker compose up${NC}"
echo "    桌面应用:  ${CYAN}make desktop${NC}"
echo ""
echo "  启动后访问 ${CYAN}http://localhost:5173${NC} 打开前端界面"
echo ""
echo "  首次启动后建议:"
echo "    - 访问 Settings 页面确认 LLM 配置"
echo "    - 运行 ${CYAN}make demo${NC} 填充示例数据"
echo ""
echo "  更多帮助:  ${CYAN}cat README.md${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
