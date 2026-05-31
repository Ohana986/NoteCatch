#!/usr/bin/env bash
# NoteCatch 卸载脚本
# 用法: bash uninstall.sh
set -eu

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  NoteCatch 卸载${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ── 检测系统 ──
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS="$ID"
else
    OS="unknown"
fi

# ════════════════════════════════════════════
# 收集阶段
# ════════════════════════════════════════════

# ── 类别 1: 虚拟环境 ──
VENV_DIR="$SCRIPT_DIR/.venv"
HAS_VENV=false
if [ -d "$VENV_DIR" ]; then
    HAS_VENV=true
else
    echo -e "  ${YELLOW}⏭ 未找到虚拟环境，跳过${NC}"
fi

# ── 类别 2: pipx CLI 工具 ──
PIPX_TOOLS=("demucs" "basic-pitch")
declare -A PIPX_DESC
PIPX_DESC["demucs"]="Demucs 人声分离引擎"
PIPX_DESC["basic-pitch"]="Basic Pitch 音高检测引擎"

INSTALLED_PIPX=()
for tool in "${PIPX_TOOLS[@]}"; do
    if pipx list 2>/dev/null | grep -q "package $tool "; then
        INSTALLED_PIPX+=("$tool")
    fi
done
if [ ${#INSTALLED_PIPX[@]} -eq 0 ]; then
    echo -e "  ${YELLOW}⏭ 未找到 pipx 工具，跳过${NC}"
fi

# ── 类别 3: 系统依赖（仅提示，不自动卸载） ──
case "$OS" in
    fedora|rhel|centos)
        SYS_PKGS="python3-gobject gtk4 libadwaita gstreamer1-plugins-good gstreamer1-plugins-base pulseaudio-utils ffmpeg pipx"
        SYS_PKG_MGR="dnf"
        ;;
    debian|ubuntu)
        SYS_PKGS="python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gstreamer1.0-plugins-good gstreamer1.0-plugins-base pulseaudio-utils ffmpeg pipx"
        SYS_PKG_MGR="apt"
        ;;
    *)
        SYS_PKGS=""
        SYS_PKG_MGR=""
        ;;
esac

# ── 无任何可卸载内容 ──
if ! $HAS_VENV && [ ${#INSTALLED_PIPX[@]} -eq 0 ]; then
    echo -e "  ${GREEN}没有需要卸载的内容。${NC}"
    exit 0
fi

# ════════════════════════════════════════════
# 展示阶段
# ════════════════════════════════════════════

echo -e "${YELLOW}── 将要移除的内容 ──${NC}"
echo ""

# 类别 1
if $HAS_VENV; then
    echo -e "  ${CYAN}[1] Python 虚拟环境:${NC}"
    echo -e "      ${RED}$VENV_DIR${NC}"
    echo ""
fi

# 类别 2
if [ ${#INSTALLED_PIPX[@]} -gt 0 ]; then
    echo -e "  ${CYAN}[2] pipx 全局工具:${NC}"
    for tool in "${INSTALLED_PIPX[@]}"; do
        echo -e "      • ${RED}$tool${NC} — ${PIPX_DESC[$tool]}"
    done
    echo ""
fi

# 类别 3
if [ -n "$SYS_PKGS" ]; then
    echo -e "  ${CYAN}[3] 系统包 ${YELLOW}(仅提示，不自动删除)${NC}:"
    for pkg in $SYS_PKGS; do
        echo -e "      • $pkg"
    done
    echo ""
fi

# ════════════════════════════════════════════
# 逐项确认阶段
# ════════════════════════════════════════════

echo -e "${CYAN}────────────────────────────────────────${NC}"
echo -e "${YELLOW}请逐项确认是否删除（回答 y/N）：${NC}"
echo ""

REMOVE_VENV=false
REMOVE_PIPX=()

# ── 类别 1: 虚拟环境 ──
if $HAS_VENV; then
    read -r -p "$(echo -e "  ${RED}删除虚拟环境 .venv/ ?${NC} [y/N] ")" ANS
    if [[ "$ANS" =~ ^[Yy]$ ]]; then
        REMOVE_VENV=true
        echo -e "    → ${GREEN}将删除${NC}"
    else
        echo -e "    → ${YELLOW}保留${NC}"
    fi
    echo ""
fi

# ── 类别 2: pipx 工具逐个确认 ──
for tool in "${INSTALLED_PIPX[@]}"; do
    read -r -p "$(echo -e "  ${RED}卸载 pipx 工具: $tool (${PIPX_DESC[$tool]}) ?${NC} [y/N] ")" ANS
    if [[ "$ANS" =~ ^[Yy]$ ]]; then
        REMOVE_PIPX+=("$tool")
        echo -e "    → ${GREEN}将卸载${NC}"
    else
        echo -e "    → ${YELLOW}保留${NC}"
    fi
    echo ""
done

# ── 检查是否有确认的操作 ──
if ! $REMOVE_VENV && [ ${#REMOVE_PIPX[@]} -eq 0 ]; then
    echo -e "  ${GREEN}没有选择任何操作，退出。${NC}"
    exit 0
fi

# ── 最终确认 ──
echo -e "${CYAN}────────────────────────────────────────${NC}"
echo -e "${YELLOW}── 最终确认：将执行以下操作 ──${NC}"
echo ""
if $REMOVE_VENV; then
    echo -e "  ${RED}• 删除虚拟环境: $VENV_DIR${NC}"
fi
for tool in "${REMOVE_PIPX[@]}"; do
    echo -e "  ${RED}• pipx uninstall $tool${NC}"
done
echo ""
read -r -p "$(echo -e "${RED}确认执行？${NC} [y/N] ")" CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    exit 0
fi

echo ""

# ════════════════════════════════════════════
# 执行阶段
# ════════════════════════════════════════════

# ── 1) 虚拟环境 ──
if $REMOVE_VENV; then
    echo -e "${CYAN}── 移除虚拟环境 ──${NC}"
    rm -rf "$VENV_DIR"
    echo -e "  ${GREEN}✅ 已移除${NC}"
    echo ""
fi

# ── 2) pipx 工具 ──
if [ ${#REMOVE_PIPX[@]} -gt 0 ]; then
    echo -e "${CYAN}── 卸载 pipx 工具 ──${NC}"
    for tool in "${REMOVE_PIPX[@]}"; do
        pipx uninstall "$tool"
        echo -e "  ${GREEN}✅ $tool 已卸载${NC}"
    done
    echo ""
fi

# ── 完成 ──
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  卸载完成${NC}"

# ── 3) 提示系统依赖 ──
if [ -n "$SYS_PKGS" ]; then
    echo ""
    echo -e "  ${YELLOW}⚠ 系统包未自动移除（可能被其他程序使用）：${NC}"
    echo "      $SYS_PKGS"
    echo ""
    echo -e "  如需移除，请手动执行："
    case "$SYS_PKG_MGR" in
        dnf)
            echo -e "      ${YELLOW}sudo dnf remove $SYS_PKGS${NC}"
            ;;
        apt)
            echo -e "      ${YELLOW}sudo apt remove $SYS_PKGS${NC}"
            ;;
    esac
fi

echo ""
# 提示哪些项目被保留
if $HAS_VENV && ! $REMOVE_VENV; then
    echo -e "  ${YELLOW}💡 虚拟环境已保留: $VENV_DIR${NC}"
fi
for tool in "${PIPX_TOOLS[@]}"; do
    kept=true
    for removed in "${REMOVE_PIPX[@]}"; do
        [ "$tool" = "$removed" ] && kept=false && break
    done
    for installed in "${INSTALLED_PIPX[@]}"; do
        if $kept && [ "$tool" = "$installed" ]; then
            echo -e "  ${YELLOW}💡 pipx 工具已保留: $tool${NC}"
        fi
    done
done
echo -e "  ${YELLOW}💡 recordings/ 目录（录音数据）未被删除，如需清理请手动操作。${NC}"
echo -e "${CYAN}========================================${NC}"