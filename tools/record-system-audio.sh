#!/usr/bin/env bash
# 录制系统播放音频
# 用法: ./record-system-audio.sh [时长秒数]
#       不加时长则手动 Ctrl+C 停止

set -eu

# 强制英文 locale，避免 pactl 中文输出导致解析失败
export LANG=C

BASENAME="系统录音_$(date +%Y%m%d_%H%M%S)"
OUTDIR="$(dirname "$0")/../recordings/${BASENAME}"
mkdir -p "$OUTDIR"

# --- 查找当前有音频输出的 sink（取第一个 RUNNING 的）---
SINK=$(pactl list sinks short | awk '$NF == "RUNNING" {print $2; exit}')

if [ -z "$SINK" ]; then
    SINK=$(pactl list sinks short | head -1 | awk '{print $2}')
fi

if [ -z "$SINK" ]; then
    echo "错误：找不到音频输出设备" >&2
    exit 1
fi

# --- 从 sink 读取原生采样规格 ---
spec=$(pactl list sinks | sed -n "/Name: ${SINK}$/,/^$/p" | grep "Sample Specification" | sed 's/.*Sample Specification: //')
native_fmt=$(echo "$spec" | awk '{print $1}')
native_rate=$(echo "$spec" | awk '{print $3}' | sed 's/Hz//')
# 兜底
[ -z "$native_fmt" ] && native_fmt="s16le"
[ -z "$native_rate" ] && native_rate="48000"

DEVICE="${SINK}.monitor"
OUTFILE="${OUTDIR}/${BASENAME}.wav"

echo "输出设备: ${SINK}"
echo "原生规格: ${native_fmt} ${native_rate}Hz"
echo "输出目录: ${OUTDIR}"
echo "输出文件: ${OUTFILE}"
echo "--- 开始录制（${1:+限时 ${1} 秒}${1:-按 Ctrl+C 停止}）---"

RC=0
if [ $# -ge 1 ] && [ "$1" -gt 0 ] 2>/dev/null; then
    timeout "$1" parecord \
        --device="$DEVICE" \
        --channels=2 \
        --format="$native_fmt" \
        --rate="$native_rate" \
        "$OUTFILE" || RC=$?
    # timeout 返回 124 表示正常超时终止，不是错误
    if [ "$RC" -eq 124 ] || [ "$RC" -eq 0 ]; then
        echo "录制完成：${OUTFILE}"
    else
        echo "录制失败（退出码 ${RC}）" >&2
        exit "$RC"
    fi
else
    parecord \
        --device="$DEVICE" \
        --channels=2 \
        --format="$native_fmt" \
        --rate="$native_rate" \
        "$OUTFILE"
fi