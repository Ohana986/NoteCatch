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

# ════════════════════════════════════════════
# 语言检测（与 Python i18n 逻辑一致）
# ════════════════════════════════════════════

detect_lang() {
    if [ -n "${NOTECATCH_LANG:-}" ]; then
        echo "$NOTECATCH_LANG"
        return
    fi
    case "${LANG:-}" in
        zh_*|zh-*) echo "zh" ;;
        *)          echo "en" ;;
    esac
}
LANG_CODE=$(detect_lang)

# 翻译函数：中文原文 → 英文翻译
_() {
    if [ "$LANG_CODE" != "en" ]; then
        echo "$1"
        return
    fi
    case "$1" in
        # ── 标题 ──
        "NoteCatch 卸载")                  echo "NoteCatch Uninstall" ;;
        # ── 收集 ──
        "未找到虚拟环境，跳过")             echo "Virtual environment not found, skipping" ;;
        "未找到 pipx 工具，跳过")           echo "No pipx tools found, skipping" ;;
        "没有需要卸载的内容")               echo "Nothing to uninstall" ;;
        # ── 展示 ──
        "将要移除的内容")                   echo "Items to be removed" ;;
        "Python 虚拟环境:")                 echo "Python Virtual Environment:" ;;
        "pipx 全局工具:")                   echo "pipx Global Tools:" ;;
        "(仅提示，不自动删除)")             echo "(hint only, will not remove)" ;;
        # ── 工具描述 ──
        "Demucs 人声分离引擎")              echo "Demucs Vocal Separation Engine" ;;
        "Basic Pitch 音高检测引擎")         echo "Basic Pitch Pitch Detection Engine" ;;
        # ── 逐项确认 ──
        "请逐项确认是否删除（回答 y/N）：") echo "Confirm each item (y/N):" ;;
        "删除虚拟环境 .venv/ ?")            echo "Remove virtual environment .venv/ ?" ;;
        "将删除")                           echo "Will remove" ;;
        "保留")                             echo "Keep" ;;
        "卸载 pipx 工具: %s (%s) ?")        echo "Uninstall pipx tool: %s (%s) ?" ;;
        "没有选择任何操作，退出")           echo "No operation selected, exiting" ;;
        # ── 最终确认 ──
        "最终确认：将执行以下操作")         echo "Final confirmation — will execute:" ;;
        "确认执行？[y/N]")                  echo "Confirm execution? [y/N]" ;;
        "已取消")                           echo "Cancelled" ;;
        # ── 执行 ──
        "移除虚拟环境")                     echo "Removing virtual environment" ;;
        "已移除")                           echo "Removed" ;;
        "卸载 pipx 工具")                   echo "Uninstalling pipx tools" ;;
        "%s 已卸载")                        echo "%s uninstalled" ;;
        "卸载完成")                         echo "Uninstall complete" ;;
        # ── 系统包提示 ──
        "系统包未自动移除（可能被其他程序使用）：")
            echo "System packages not removed (may be used by other programs):" ;;
        "如需移除，请手动执行：")           echo "To remove, run manually:" ;;
        # ── 保留提示 ──
        "虚拟环境已保留: %s")               echo "Virtual environment kept:" ;;
        "pipx 工具已保留: %s")              echo "pipx tool kept:" ;;
        "recordings/ 目录（录音数据）未被删除，如需清理请手动操作")
            echo "recordings/ directory (recording data) not deleted; remove manually if needed" ;;
        # ── 默认 ──
        *) echo "$1" ;;
    esac
}

# ════════════════════════════════════════════

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  $(echo "$(_ "NoteCatch 卸载")")${NC}"
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
    echo -e "  ${YELLOW}⏭ $(_ "未找到虚拟环境，跳过")${NC}"
fi

# ── 类别 2: pipx CLI 工具 ──
PIPX_TOOLS=("demucs" "basic-pitch")
declare -A PIPX_DESC
PIPX_DESC["demucs"]="$(_ "Demucs 人声分离引擎")"
PIPX_DESC["basic-pitch"]="$(_ "Basic Pitch 音高检测引擎")"

INSTALLED_PIPX=()
for tool in "${PIPX_TOOLS[@]}"; do
    if pipx list 2>/dev/null | grep -q "package $tool "; then
        INSTALLED_PIPX+=("$tool")
    fi
done
if [ ${#INSTALLED_PIPX[@]} -eq 0 ]; then
    echo -e "  ${YELLOW}⏭ $(_ "未找到 pipx 工具，跳过")${NC}"
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
    echo -e "  ${GREEN}$(_ "没有需要卸载的内容")。${NC}"
    exit 0
fi

# ════════════════════════════════════════════
# 展示阶段
# ════════════════════════════════════════════

echo -e "${YELLOW}$(_ "将要移除的内容")${NC}"
echo ""

# 类别 1
if $HAS_VENV; then
    echo -e "  ${CYAN}[1] $(_ "Python 虚拟环境:")${NC}"
    echo -e "      ${RED}$VENV_DIR${NC}"
    echo ""
fi

# 类别 2
if [ ${#INSTALLED_PIPX[@]} -gt 0 ]; then
    echo -e "  ${CYAN}[2] $(_ "pipx 全局工具:")${NC}"
    for tool in "${INSTALLED_PIPX[@]}"; do
        echo -e "      • ${RED}$tool${NC} — ${PIPX_DESC[$tool]}"
    done
    echo ""
fi

# 类别 3
if [ -n "$SYS_PKGS" ]; then
    echo -e "  ${CYAN}[3] $(_ "系统包") ${YELLOW}$(_ "(仅提示，不自动删除)")${NC}:"
    for pkg in $SYS_PKGS; do
        echo -e "      • $pkg"
    done
    echo ""
fi

# ════════════════════════════════════════════
# 逐项确认阶段
# ════════════════════════════════════════════

echo -e "${CYAN}────────────────────────────────────────${NC}"
echo -e "${YELLOW}$(_ "请逐项确认是否删除（回答 y/N）：")${NC}"
echo ""

REMOVE_VENV=false
REMOVE_PIPX=()

# ── 类别 1: 虚拟环境 ──
if $HAS_VENV; then
    read -r -p "$(echo -e "  ${RED}$(_ "删除虚拟环境 .venv/ ?")${NC} [y/N] ")" ANS
    if [[ "$ANS" =~ ^[Yy]$ ]]; then
        REMOVE_VENV=true
        echo -e "    → ${GREEN}$(_ "将删除")${NC}"
    else
        echo -e "    → ${YELLOW}$(_ "保留")${NC}"
    fi
    echo ""
fi

# ── 类别 2: pipx 工具逐个确认 ──
for tool in "${INSTALLED_PIPX[@]}"; do
    read -r -p "$(echo -e "  ${RED}$(printf "$(_ "卸载 pipx 工具: %s (%s) ?")" "$tool" "${PIPX_DESC[$tool]}")${NC} [y/N] ")" ANS
    if [[ "$ANS" =~ ^[Yy]$ ]]; then
        REMOVE_PIPX+=("$tool")
        echo -e "    → ${GREEN}$(_ "将删除")${NC}"
    else
        echo -e "    → ${YELLOW}$(_ "保留")${NC}"
    fi
    echo ""
done

# ── 检查是否有确认的操作 ──
if ! $REMOVE_VENV && [ ${#REMOVE_PIPX[@]} -eq 0 ]; then
    echo -e "  ${GREEN}$(_ "没有选择任何操作，退出")。${NC}"
    exit 0
fi

# ── 最终确认 ──
echo -e "${CYAN}────────────────────────────────────────${NC}"
echo -e "${YELLOW}$(_ "最终确认：将执行以下操作")${NC}"
echo ""
if $REMOVE_VENV; then
    echo -e "  ${RED}• $(_ "删除虚拟环境 .venv/ ?"): $VENV_DIR${NC}"
fi
for tool in "${REMOVE_PIPX[@]}"; do
    echo -e "  ${RED}• pipx uninstall $tool${NC}"
done
echo ""
read -r -p "$(echo -e "${RED}$(_ "确认执行？[y/N]")${NC} ")" CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "$(_ "已取消")"
    exit 0
fi

echo ""

# ════════════════════════════════════════════
# 执行阶段
# ════════════════════════════════════════════

# ── 1) 虚拟环境 ──
if $REMOVE_VENV; then
    echo -e "${CYAN}$(_ "移除虚拟环境")${NC}"
    rm -rf "$VENV_DIR"
    echo -e "  ${GREEN}✅ $(_ "已移除")${NC}"
    echo ""
fi

# ── 2) pipx 工具 ──
if [ ${#REMOVE_PIPX[@]} -gt 0 ]; then
    echo -e "${CYAN}$(_ "卸载 pipx 工具")${NC}"
    for tool in "${REMOVE_PIPX[@]}"; do
        pipx uninstall "$tool"
        echo -e "  ${GREEN}✅ $(printf "$(_ "%s 已卸载")" "$tool")${NC}"
    done
    echo ""
fi

# ── 完成 ──
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  $(_ "卸载完成")${NC}"

# ── 3) 提示系统依赖 ──
if [ -n "$SYS_PKGS" ]; then
    echo ""
    echo -e "  ${YELLOW}⚠ $(_ "系统包未自动移除（可能被其他程序使用）：")${NC}"
    echo "      $SYS_PKGS"
    echo ""
    echo -e "  $(_ "如需移除，请手动执行：")"
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
    echo -e "  ${YELLOW}💡 $(printf "$(_ "虚拟环境已保留: %s")" "$VENV_DIR")${NC}"
fi
for tool in "${PIPX_TOOLS[@]}"; do
    kept=true
    for removed in "${REMOVE_PIPX[@]}"; do
        [ "$tool" = "$removed" ] && kept=false && break
    done
    for installed in "${INSTALLED_PIPX[@]}"; do
        if $kept && [ "$tool" = "$installed" ]; then
            echo -e "  ${YELLOW}💡 $(printf "$(_ "pipx 工具已保留: %s")" "$tool")${NC}"
        fi
    done
done
echo -e "  ${YELLOW}💡 $(_ "recordings/ 目录（录音数据）未被删除，如需清理请手动操作")${NC}"
echo -e "${CYAN}========================================${NC}"