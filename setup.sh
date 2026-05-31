#!/usr/bin/env bash
# NoteCatch 一键安装脚本
# 用法: bash setup.sh
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
        "NoteCatch 环境安装")            echo "NoteCatch Environment Setup" ;;
        # ── Python ──
        "❌ 未找到 python3，请先安装 Python 3.10+")
            echo "python3 not found, please install Python 3.10+" ;;
        "✅ Python $PYVER")              echo "Python $PYVER" ;;
        # ── 类别标签 ──
        "系统依赖 (%s)")                 echo "System Dependencies (%s)" ;;
        "系统依赖（未知系统，请手动安装以下包）")
            echo "System Dependencies (unknown OS, please install manually)" ;;
        "Python 虚拟环境")               echo "Python Virtual Environment" ;;
        "pip 依赖")                      echo "pip Dependencies" ;;
        "pipx CLI 工具")                 echo "pipx CLI Tools" ;;
        # ── 展示 ──
        "将要执行的操作")                echo "Operations to perform" ;;
        "（已存在，将跳过创建）")         echo "(already exists, will skip)" ;;
        "创建 %s")                       echo "Create %s" ;;
        # ── 确认 ──
        "是否继续？[y/N]")               echo "Continue? [y/N]" ;;
        "已取消")                        echo "Cancelled" ;;
        # ── 执行状态 ──
        "完成")                          echo "Done" ;;
        "⏭ 已安装，跳过")               echo "Already installed, skipping" ;;
        "取消")                          echo "Cancel" ;;
        # ── 完成 ──
        "安装完成！")                    echo "Setup complete!" ;;
        "使用方式：")                    echo "Usage:" ;;
        "或直接运行：")                  echo "Or run directly:" ;;
        # ── 工具描述 ──
        "AI 音源分离引擎（人声/伴奏隔离）") echo "AI music source separation (vocal/instrumental isolation)" ;;
        "轻量级音高检测与 MIDI 转换")     echo "Lightweight pitch detection & MIDI conversion" ;;
        "Python GTK 图形绑定")            echo "Python GTK graphical bindings" ;;
        "GTK4 图形界面工具包")            echo "GTK4 GUI toolkit" ;;
        "Adwaita 现代 GNOME 应用组件")    echo "Adwaita modern GNOME app widgets" ;;
        "GStreamer 音频编解码器")         echo "GStreamer audio codecs" ;;
        "GStreamer 基础插件")             echo "GStreamer base plugins" ;;
        "系统音频采集工具 (parecord)")    echo "System audio capture utility (parecord)" ;;
        "音频/视频格式转换工具")          echo "Audio/video format conversion tool" ;;
        "隔离式 Python CLI 工具管理器")   echo "Isolated Python CLI tool manager" ;;
        # ── 默认 ──
        *) echo "$1" ;;
    esac
}

# ════════════════════════════════════════════

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  $(echo "$(_ "NoteCatch 环境安装")")${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ── 检测系统 ──
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS="$ID"
else
    OS="unknown"
fi

# ── 检查 Python ──
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}$(_ "❌ 未找到 python3，请先安装 Python 3.10+")${NC}"
    exit 1
fi
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}$(echo "$(_ "✅ Python \$PYVER")" | sed "s/\$PYVER/$PYVER/")${NC}"
echo ""

# ════════════════════════════════════════════
# 收集所有操作
# ════════════════════════════════════════════

# ── 工具描述 ──
declare -A TOOL_DESC
TOOL_DESC["demucs"]="Demucs — $(_ "AI 音源分离引擎（人声/伴奏隔离）")"
TOOL_DESC["basic-pitch"]="Basic Pitch — $(_ "轻量级音高检测与 MIDI 转换")"

declare -A SYS_PKG_DESC
SYS_PKG_DESC["python3-gobject"]="python3-gobject — $(_ "Python GTK 图形绑定")"
SYS_PKG_DESC["python3-gi"]="python3-gi — $(_ "Python GTK 图形绑定")"
SYS_PKG_DESC["gtk4"]="gtk4 — $(_ "GTK4 图形界面工具包")"
SYS_PKG_DESC["gir1.2-gtk-4.0"]="gir1.2-gtk-4.0 — $(_ "GTK4 图形界面工具包")"
SYS_PKG_DESC["libadwaita"]="libadwaita — $(_ "Adwaita 现代 GNOME 应用组件")"
SYS_PKG_DESC["gir1.2-adw-1"]="gir1.2-adw-1 — $(_ "Adwaita 现代 GNOME 应用组件")"
SYS_PKG_DESC["gstreamer1-plugins-good"]="gstreamer1-plugins-good — $(_ "GStreamer 音频编解码器")"
SYS_PKG_DESC["gstreamer1.0-plugins-good"]="gstreamer1.0-plugins-good — $(_ "GStreamer 音频编解码器")"
SYS_PKG_DESC["gstreamer1-plugins-base"]="gstreamer1-plugins-base — $(_ "GStreamer 基础插件")"
SYS_PKG_DESC["gstreamer1.0-plugins-base"]="gstreamer1.0-plugins-base — $(_ "GStreamer 基础插件")"
SYS_PKG_DESC["pulseaudio-utils"]="pulseaudio-utils — $(_ "系统音频采集工具 (parecord)")"
SYS_PKG_DESC["ffmpeg"]="ffmpeg — $(_ "音频/视频格式转换工具")"
SYS_PKG_DESC["pipx"]="pipx — $(_ "隔离式 Python CLI 工具管理器")"

# ── 1) 系统依赖 ──
case "$OS" in
    fedora|rhel|centos)
        SYS_PKGS=("python3-gobject" "gtk4" "libadwaita" "gstreamer1-plugins-good" "gstreamer1-plugins-base" "pulseaudio-utils" "ffmpeg" "pipx")
        SYS_CMD="sudo dnf install -y ${SYS_PKGS[*]}"
        SYS_LABEL=$(printf "$(_ "系统依赖 (%s)")" "dnf")
        ;;
    debian|ubuntu)
        SYS_PKGS=("python3-gi" "gir1.2-gtk-4.0" "gir1.2-adw-1" "gstreamer1.0-plugins-good" "gstreamer1.0-plugins-base" "pulseaudio-utils" "ffmpeg" "pipx")
        SYS_CMD="sudo apt update && sudo apt install -y ${SYS_PKGS[*]}"
        SYS_LABEL=$(printf "$(_ "系统依赖 (%s)")" "apt")
        ;;
    *)
        SYS_PKGS=()
        SYS_CMD=""
        SYS_LABEL=$(_ "系统依赖（未知系统，请手动安装以下包）")
        SYS_MANUAL="python3-gobject, gtk4, libadwaita, gstreamer1-plugins-good, pulseaudio-utils, ffmpeg, pipx"
        ;;
esac

# ── 2) Python 虚拟环境 ──
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_EXISTS=false
[ -d "$VENV_DIR" ] && VENV_EXISTS=true

# ── 3) pip 依赖 ──
PIP_PKGS=()
while IFS= read -r line; do
    line="${line%%#*}"
    line="$(echo "$line" | xargs)"
    [ -n "$line" ] && PIP_PKGS+=("$line")
done < "$SCRIPT_DIR/requirements.txt"

# ── 4) pipx CLI 工具 ──
PIPX_TOOLS=("demucs" "basic-pitch")

# ════════════════════════════════════════════
# 展示所有操作
# ════════════════════════════════════════════

echo -e "${YELLOW}$(_ "将要执行的操作")${NC}"
echo ""

# 1 - 系统依赖
echo -e "  ${GREEN}1.${NC} $SYS_LABEL"
if [ ${#SYS_PKGS[@]} -gt 0 ]; then
    for pkg in "${SYS_PKGS[@]}"; do
        desc="${SYS_PKG_DESC[$pkg]:-}"
        if [ -n "$desc" ]; then
            echo "      • $desc"
        else
            echo "      • $pkg"
        fi
    done
else
    echo "      $SYS_MANUAL"
fi
echo ""

# 2 - venv
echo -en "  ${GREEN}2.${NC} $(_ "Python 虚拟环境"): "
if $VENV_EXISTS; then
    echo -e "$VENV_DIR ${YELLOW}$(_ "（已存在，将跳过创建）")${NC}"
else
    printf "$(_ "创建 %s")\n" "$VENV_DIR"
fi
echo ""

# 3 - pip 依赖
echo -e "  ${GREEN}3.${NC} $(_ "pip 依赖"):"
for pkg in "${PIP_PKGS[@]}"; do
    echo "      • $pkg"
done
echo ""

# 4 - pipx 工具
echo -e "  ${GREEN}4.${NC} $(_ "pipx CLI 工具"):"
for tool in "${PIPX_TOOLS[@]}"; do
    echo "      • ${TOOL_DESC[$tool]}"
done
echo ""

# ── 确认 ──
read -r -p "$(echo -e "${YELLOW}$(_ "是否继续？[y/N]")${NC} ")" CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "$(_ "已取消")"
    exit 0
fi

echo ""

# ════════════════════════════════════════════
# 执行
# ════════════════════════════════════════════

TOTAL=4

# ── 1) 系统依赖 ──
echo -e "${CYAN}── [1/$TOTAL] $SYS_LABEL ──${NC}"
if [ -n "$SYS_CMD" ]; then
    eval "$SYS_CMD"
    echo -e "  ${GREEN}✅ $(_ "完成")${NC}"
else
    echo -e "  ${YELLOW}⚠ $(_ "请手动安装"): $SYS_MANUAL${NC}"
fi
echo ""

# ── 2) 虚拟环境 ──
echo -e "${CYAN}── [2/$TOTAL] $(_ "Python 虚拟环境") ──${NC}"
if $VENV_EXISTS; then
    echo "  ⏭ $(_ "（已存在，将跳过创建）")"
else
    python3 -m venv "$VENV_DIR"
    echo -e "  ${GREEN}✅ $(_ "完成")${NC}"
fi
echo ""

# ── 3) pip 依赖 ──
echo -e "${CYAN}── [3/$TOTAL] $(_ "pip 依赖") ──${NC}"
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
echo -e "  ${GREEN}✅ $(_ "完成")${NC}"
echo ""

# ── 4) pipx CLI 工具 ──
echo -e "${CYAN}── [4/$TOTAL] $(_ "pipx CLI 工具") ──${NC}"
for tool in "${PIPX_TOOLS[@]}"; do
    if pipx list 2>/dev/null | grep -q "package $tool "; then
        echo "  ⏭ $tool $(_ "⏭ 已安装，跳过")"
    else
        pipx install "$tool"
        echo -e "  ${GREEN}✅ $tool $(_ "完成")${NC}"
    fi
done
echo ""

# ── 完成 ──
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  $(_ "安装完成！")${NC}"
echo ""
echo -e "  $(_ "使用方式：")"
echo -e "    ${GREEN}source .venv/bin/activate${NC}"
echo -e "    cd tools"
echo -e "    python gui.py"
echo ""
echo -e "  $(_ "或直接运行：")"
echo -e "    ${GREEN}.venv/bin/python tools/gui.py${NC}"
echo -e "${CYAN}========================================${NC}"