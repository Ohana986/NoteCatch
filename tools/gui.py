# /// script
# dependencies = []
# ///

"""
录音分析 GUI — GNOME 风格 (GTK4 + Adwaita + GStreamer)

使用:
    python3 gui.py

依赖系统包: gtk4, libadwaita, python3-gobject, gstreamer1.0, pulseaudio-utils
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Adw, GLib, Gio, Gst, Gdk
import subprocess
import os
import sys
import signal
import threading
import time
import math
import re
import shutil
from pathlib import Path

Gst.init(None)

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))
from common import resolve_paths


# ──────────────────────────────────────────────
# 波形 LOGO (Cairo 绘制)
# ──────────────────────────────────────────────
class WaveformLogo(Gtk.DrawingArea):
    """自定义波形图案。"""

    def __init__(self, width=240, height=90):
        super().__init__()
        self.set_size_request(width, height)
        self.set_draw_func(self._draw, None)

    def _draw(self, area, cr, w, h, data):
        cr.set_source_rgb(0.96, 0.96, 0.97)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        n = 36
        gap = w / n
        bar_w = gap * 0.55
        for i in range(n):
            t = (i - n / 2) / (n / 2)
            envelope = max(0, 1 - abs(t) * 0.6)
            val = math.sin(i * 0.45) * 0.6 + math.sin(i * 0.9) * 0.3
            bar_h = int(h * 0.35 * envelope * (0.4 + 0.6 * abs(val)))
            if bar_h < 3:
                bar_h = 3
            x = i * gap + (gap - bar_w) / 2
            y0 = (h - bar_h) / 2
            r = 0.33 + 0.1 * abs(val)
            g = 0.42 + 0.15 * abs(val)
            b = 0.78 + 0.1 * abs(val)
            cr.set_source_rgb(r, g, b)
            cr.set_line_width(bar_w)
            cr.set_line_cap(1)
            cr.move_to(x + bar_w / 2, y0)
            cr.line_to(x + bar_w / 2, y0 + bar_h)
            cr.stroke()


# ──────────────────────────────────────────────
# 查找音频 Sink（locale 无关）
# ──────────────────────────────────────────────
def find_recording_sink():
    """返回 (sink_id, format, rate) 或 None。使用 LANG=C 避免中文 locale 问题。"""
    env_c = os.environ.copy()
    env_c["LANG"] = "C"
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sinks", "short"],
            text=True, stderr=subprocess.DEVNULL, env=env_c,
        )
        sink_id = None
        for line in out.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2 and parts[-1].upper() == "RUNNING":
                sink_id = parts[0]
                break
        if sink_id is None and out.strip():
            sink_id = out.strip().split("\n")[0].split()[0]
        if sink_id is None:
            return None

        long_out = subprocess.check_output(
            ["pactl", "list", "sinks"],
            text=True, stderr=subprocess.DEVNULL, env=env_c,
        )
        fmt = "s16le"
        rate = "48000"
        in_target = False
        for line in long_out.split("\n"):
            m_id = re.match(r"Sink\s+#(\d+)", line)
            if m_id:
                in_target = (m_id.group(1) == sink_id)
                continue
            if not in_target:
                continue
            m_spec = re.search(r"Sample Specification:\s*(.+)", line)
            if m_spec:
                spec_raw = m_spec.group(1).strip()
                parts = spec_raw.split()
                if parts:
                    fmt = parts[0]
                rate_m = re.search(r"(\d+)\s*Hz", spec_raw)
                if rate_m:
                    rate = rate_m.group(1)
                continue
        return (sink_id, fmt, rate)
    except Exception as e:
        print(f"查找音频设备失败: {e}", file=sys.stderr)
        return None


# ──────────────────────────────────────────────
# 录音文件列表行
# ──────────────────────────────────────────────
class RecordingRow(Gtk.ListBoxRow):
    """每行：播放(含拖动进度) / 处理 / 隐藏 / 删除。"""

    def __init__(self, filepath, on_process, on_hide, on_delete, app):
        super().__init__()
        self.filepath = filepath
        self.basename = os.path.basename(filepath)
        self._app = app  # RecorderApp 引用，用于独占播放协调

        # ── GStreamer 播放器 ──
        self._player: Gst.Element | None = None
        self._bus_watch_id: int = 0
        self._pos_update_id: int = 0
        self._duration_ns: int = 0
        self._seeking: bool = False  # 用户正在拖动时跳过自动更新

        # ── 顶层垂直容器 ──
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # ── 主行 ──
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row.set_margin_top(4)
        row.set_margin_bottom(4)
        row.set_margin_start(8)
        row.set_margin_end(8)

        icon = Gtk.Image(icon_name="audio-x-generic-symbolic")
        icon.set_margin_end(6)
        row.append(icon)

        name_label = Gtk.Label(
            label=self.basename,
            xalign=0,
            hexpand=True,
            ellipsize=3,
        )
        name_label.add_css_class("body")
        row.append(name_label)

        # 播放按钮
        self.play_btn = Gtk.Button(label="播放")
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self.play_btn.add_css_class("flat")
        self.play_btn.add_css_class("compact")
        self.play_btn.set_tooltip_text("播放 / 暂停")
        self.play_btn.connect("clicked", self._on_play_toggle)
        row.append(self.play_btn)

        # 开始处理
        self.process_btn = Gtk.Button(label="处理")
        self.process_btn.set_icon_name("emblem-system-symbolic")
        self.process_btn.add_css_class("flat")
        self.process_btn.add_css_class("compact")
        self.process_btn.set_tooltip_text("Demucs 人声分离 + Basic Pitch → MIDI")
        self.process_btn.connect("clicked", lambda b: on_process(self))
        row.append(self.process_btn)

        # 隐藏
        hide_btn = Gtk.Button(label="隐藏")
        hide_btn.set_icon_name("eye-not-looking-symbolic")
        hide_btn.add_css_class("flat")
        hide_btn.add_css_class("compact")
        hide_btn.set_tooltip_text("从列表隐藏（保留文件）")
        hide_btn.connect("clicked", lambda b: on_hide(self))
        row.append(hide_btn)

        # 删除
        delete_btn = Gtk.Button(label="删除")
        delete_btn.set_icon_name("user-trash-symbolic")
        delete_btn.add_css_class("flat")
        delete_btn.add_css_class("compact")
        delete_btn.add_css_class("destructive-action")
        delete_btn.set_tooltip_text("删除录音及全部关联生成文件")
        delete_btn.connect("clicked", lambda b: on_delete(self))
        row.append(delete_btn)

        outer.append(row)

        # ── 播放进度区域 ──
        self._play_revealer = Gtk.Revealer()
        self._play_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._play_revealer.set_transition_duration(200)

        play_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        play_box.set_margin_start(36)
        play_box.set_margin_end(12)
        play_box.set_margin_bottom(6)

        self._play_label = Gtk.Label(label="", xalign=0)
        self._play_label.add_css_class("caption")
        play_box.append(self._play_label)

        # 拖动进度条
        self._play_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 100.0, 1.0)
        self._play_scale.set_draw_value(False)
        self._play_scale.set_hexpand(True)
        self._play_scale.set_sensitive(False)
        self._play_scale.connect("change-value", self._on_scale_drag)
        play_box.append(self._play_scale)

        self._play_revealer.set_child(play_box)
        outer.append(self._play_revealer)

        # ── 处理进度区域 ──
        self._proc_revealer = Gtk.Revealer()
        self._proc_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._proc_revealer.set_transition_duration(200)

        proc_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        proc_box.set_margin_start(36)
        proc_box.set_margin_end(12)
        proc_box.set_margin_bottom(6)

        self._proc_label = Gtk.Label(label="", xalign=0)
        self._proc_label.add_css_class("caption")
        proc_box.append(self._proc_label)

        self._proc_bar = Gtk.ProgressBar(hexpand=True)
        proc_box.append(self._proc_bar)

        self._proc_revealer.set_child(proc_box)
        outer.append(self._proc_revealer)

        self.set_child(outer)

        self._playing = False
        self._paused = False
        self._processed = False

        # 检测是否已处理过（产物已存在）
        if self._outputs_exist():
            self._mark_processed()

    def _outputs_exist(self) -> bool:
        """检查处理产物是否已存在。"""
        paths = resolve_paths(self.filepath)
        return os.path.isfile(paths["vocals"]) and os.path.isfile(paths["midi"])

    def _mark_processed(self):
        """标记为已处理，按钮变为绿色 ✓。"""
        self._processed = True
        self.process_btn.set_label("✓")
        self.process_btn.set_icon_name("")
        self.process_btn.add_css_class("success")
        self.process_btn.set_sensitive(False)
        self.process_btn.set_tooltip_text("处理完成")

    # ── 播放逻辑 (GStreamer) ──
    def _on_play_toggle(self, btn):
        if self._playing and not self._paused:
            # 正在播放 → 暂停
            self._pause()
        elif self._playing and self._paused:
            # 已暂停 → 继续
            self._resume()
        else:
            # 开始播放
            self._start_playback()

    def _start_playback(self):
        if not os.path.isfile(self.filepath):
            return

        # 独占播放：先停掉前一个
        self._app._stop_other_player(self)

        # 清理旧 pipeline（如果有）
        self._cleanup_player()

        # 创建新 pipeline
        uri = Gst.filename_to_uri(self.filepath)
        self._player = Gst.ElementFactory.make("playbin", None)
        if self._player is None:
            self._app._toast("无法创建 GStreamer 播放器")
            return
        self._player.set_property("uri", uri)

        # 监听 bus 消息
        bus = self._player.get_bus()
        bus.add_signal_watch()
        self._bus_watch_id = bus.connect("message", self._on_gst_message)

        # 开始播放
        ret = self._player.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self._app._toast("播放失败")
            self._cleanup_player()
            return

        self._playing = True
        self._paused = False
        self._duration_ns = 0
        self._seeking = False
        self.play_btn.set_label("暂停")
        self.play_btn.set_icon_name("media-playback-pause-symbolic")
        self._play_revealer.set_reveal_child(True)
        self._play_scale.set_value(0.0)
        self._play_scale.set_sensitive(False)
        self._play_label.set_label("▶ 播放中...")

    def _on_gst_message(self, bus, msg):
        t = msg.type
        if t == Gst.MessageType.EOS:
            # 播放结束
            GLib.idle_add(self._on_playback_end)
        elif t == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print(f"GStreamer 错误: {err}", file=sys.stderr)
            GLib.idle_add(self._on_playback_end)
        elif t == Gst.MessageType.STATE_CHANGED:
            old, new, pending = msg.parse_state_changed()
            if msg.src == self._player:
                if new == Gst.State.PAUSED and old == Gst.State.READY:
                    # 预卷完成，获取时长并开始进度更新
                    GLib.idle_add(self._on_ready)
        elif t == Gst.MessageType.DURATION_CHANGED:
            GLib.idle_add(self._update_duration)

    def _on_ready(self):
        self._update_duration()
        self._play_scale.set_sensitive(True)
        self._start_position_updates()

    def _update_duration(self):
        if self._player is None:
            return
        ok, dur = self._player.query_duration(Gst.Format.TIME)
        if ok:
            self._duration_ns = dur
            self._play_scale.set_range(0.0, dur / Gst.SECOND)

    def _start_position_updates(self):
        if self._pos_update_id:
            GLib.source_remove(self._pos_update_id)
        self._pos_update_id = GLib.timeout_add(200, self._update_position)

    def _update_position(self):
        if self._player is None or self._seeking:
            return True  # 继续轮询
        ok, pos = self._player.query_position(Gst.Format.TIME)
        if ok and self._duration_ns > 0:
            seconds = pos / Gst.SECOND
            dur_sec = self._duration_ns / Gst.SECOND
            frac = seconds / dur_sec if dur_sec > 0 else 0
            self._play_scale.set_value(seconds)
            m = int(seconds // 60)
            s = int(seconds % 60)
            self._play_label.set_label(f"▶ {m}:{s:02d}")
        return True  # 继续轮询

    def _on_scale_drag(self, scale, scroll, value):
        """用户拖动进度条时触发。"""
        if self._player is None:
            return
        self._seeking = True
        seek_ns = int(value * Gst.SECOND)
        self._player.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            seek_ns)
        # 短延迟后恢复位置更新
        GLib.timeout_add(300, self._clear_seeking)
        m = int(value // 60)
        s = int(value % 60)
        self._play_label.set_label(f"▶ {m}:{s:02d}")

    def _clear_seeking(self):
        self._seeking = False

    def _pause(self):
        if self._player is None:
            return
        self._player.set_state(Gst.State.PAUSED)
        self._paused = True
        self.play_btn.set_label("继续")
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self._play_label.set_label("⏸ 已暂停")
        if self._pos_update_id:
            GLib.source_remove(self._pos_update_id)
            self._pos_update_id = 0

    def _resume(self):
        if self._player is None:
            return
        self._player.set_state(Gst.State.PLAYING)
        self._paused = False
        self.play_btn.set_label("暂停")
        self.play_btn.set_icon_name("media-playback-pause-symbolic")
        self._play_label.set_label("▶ 播放中...")
        self._start_position_updates()

    def stop_playback(self):
        """从外部停止播放（被新播放条目抢占时调用）。"""
        if self._player is not None:
            self._player.set_state(Gst.State.NULL)
        self._cleanup_player()
        self._playing = False
        self._paused = False
        self.play_btn.set_label("播放")
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self._play_label.set_label("")
        self._play_revealer.set_reveal_child(False)

    def _on_playback_end(self):
        """播放自然结束。"""
        self._cleanup_player()
        self._playing = False
        self._paused = False
        self.play_btn.set_label("播放")
        self.play_btn.set_icon_name("media-playback-start-symbolic")
        self._play_scale.set_sensitive(False)
        self._play_label.set_label("播放完毕")
        GLib.timeout_add_seconds(2, self._hide_play_progress)
        self._app._on_player_done(self)

    def _cleanup_player(self):
        if self._pos_update_id:
            GLib.source_remove(self._pos_update_id)
            self._pos_update_id = 0
        if self._bus_watch_id and self._player:
            bus = self._player.get_bus()
            bus.remove_signal_watch()
            bus.disconnect(self._bus_watch_id)
            self._bus_watch_id = 0
        if self._player:
            self._player.set_state(Gst.State.NULL)
            self._player = None
        self._seeking = False

    def _hide_play_progress(self):
        self._play_revealer.set_reveal_child(False)

    # ── 处理进度 UI ──
    def show_progress(self, text, fraction):
        if not self._processed:
            self.process_btn.set_sensitive(False)
        self._proc_revealer.set_reveal_child(True)
        self._proc_label.set_label(text)
        self._proc_bar.set_fraction(fraction)

    def hide_progress(self):
        if not self._processed:
            self.process_btn.set_sensitive(True)
        self._proc_revealer.set_reveal_child(False)


# ──────────────────────────────────────────────
# 主应用
# ──────────────────────────────────────────────
class RecorderApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.audio.recorder.tool",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.recording_process = None
        self.recording_path = None
        self.recording_paused = False
        self.output_dir = SCRIPT_DIR.parent / "recordings"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rows: list[RecordingRow] = []
        self.active_row: RecordingRow | None = None
        self._playing_row: RecordingRow | None = None
        self._hidden_file = self.output_dir / ".hidden_recordings"
        self._hidden_set: set[str] = self._load_hidden()

    # ── 独占播放协调 ──
    def _stop_other_player(self, current: RecordingRow):
        """停止其他正在播放的条目。"""
        if self._playing_row is not None and self._playing_row is not current:
            self._playing_row.stop_playback()
        self._playing_row = current

    def _on_player_done(self, row: RecordingRow):
        """播放结束回调。"""
        if self._playing_row is row:
            self._playing_row = None

    def do_activate(self):
        win = Adw.ApplicationWindow(application=self)
        win.set_default_size(580, 680)
        win.set_title("录音分析工具")
        win.set_resizable(True)

        # ── CSS 样式 ──
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string("""
            .success {
                color: @success_color;
                font-weight: bold;
            }
            .icon-only {
                opacity: 0.75;
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # ── 工具箱 ──
        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_title(True)
        toolbar_view.add_top_bar(header)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)

        # ── LOGO + 标题 ──
        logo = WaveformLogo(width=220, height=80)
        logo.set_halign(Gtk.Align.CENTER)
        logo.set_margin_bottom(4)
        main_box.append(logo)

        title_label = Gtk.Label(label="录音分析工具")
        title_label.add_css_class("title-2")
        title_label.set_halign(Gtk.Align.CENTER)
        main_box.append(title_label)

        subtitle = Gtk.Label(label="录制系统音频 → 人声分离 → MIDI 五线谱")
        subtitle.add_css_class("subtitle")
        subtitle.set_halign(Gtk.Align.CENTER)
        subtitle.set_margin_bottom(6)
        main_box.append(subtitle)

        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep1.set_margin_top(8)
        sep1.set_margin_bottom(12)
        main_box.append(sep1)

        # ── 按钮行 ──
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.CENTER)

        self.record_btn = Gtk.Button(label="录音")
        self.record_btn.add_css_class("suggested-action")
        self.record_btn.set_icon_name("media-record-symbolic")
        self.record_btn.connect("clicked", self.on_record)
        btn_box.append(self.record_btn)

        self.pause_btn = Gtk.Button(label="暂停")
        self.pause_btn.set_icon_name("media-playback-pause-symbolic")
        self.pause_btn.set_sensitive(False)
        self.pause_btn.connect("clicked", self.on_pause)
        btn_box.append(self.pause_btn)

        self.stop_btn = Gtk.Button(label="终止")
        self.stop_btn.add_css_class("destructive-action")
        self.stop_btn.set_icon_name("media-playback-stop-symbolic")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", self.on_stop)
        btn_box.append(self.stop_btn)

        self.dir_btn = Gtk.Button(label="输出路径")
        self.dir_btn.set_icon_name("folder-open-symbolic")
        self.dir_btn.connect("clicked", self.on_select_output)
        btn_box.append(self.dir_btn)

        main_box.append(btn_box)

        # ── 路径显示 ──
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        path_box.set_margin_top(10)
        path_icon = Gtk.Image(icon_name="folder-symbolic")
        path_box.append(path_icon)
        self.path_label = Gtk.Label(
            label=str(self.output_dir), xalign=0, hexpand=True,
            wrap=True, wrap_mode=2,
        )
        self.path_label.add_css_class("caption")
        self.path_label.set_tooltip_text(str(self.output_dir))
        path_box.append(self.path_label)

        # 打开文件夹按钮
        open_btn = Gtk.Button()
        open_btn.set_icon_name("document-open-symbolic")
        open_btn.add_css_class("flat")
        open_btn.add_css_class("compact")
        open_btn.set_tooltip_text("在文件管理器中打开")
        open_btn.connect("clicked", self._on_open_folder)
        path_box.append(open_btn)

        main_box.append(path_box)

        # ── 录制提示 ──
        self.recording_hint = Gtk.Label(label="", xalign=0)
        self.recording_hint.add_css_class("caption")
        self.recording_hint.set_margin_top(6)
        self.recording_hint.set_margin_bottom(5)
        self.recording_hint.set_visible(False)
        main_box.append(self.recording_hint)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep2.set_margin_top(16)
        sep2.set_margin_bottom(6)
        main_box.append(sep2)

        # ── 文件列表 ──
        list_header = Gtk.Label(label="录音文件", xalign=0)
        list_header.add_css_class("heading")
        list_header.set_margin_bottom(8)
        main_box.append(list_header)

        self.file_list = Gtk.ListBox()
        self.file_list.add_css_class("boxed-list")
        self.file_list.set_selection_mode(Gtk.SelectionMode.NONE)
        main_box.append(self.file_list)

        # ── 状态栏 ──
        self.statusbar = Gtk.Label(label="就绪", xalign=0)
        self.statusbar.add_css_class("caption")
        self.statusbar.set_margin_top(10)
        self.statusbar.add_css_class("dim-label")
        main_box.append(self.statusbar)

        scrolled.set_child(main_box)
        toolbar_view.set_content(scrolled)
        win.set_content(toolbar_view)
        win.present()

        self._refresh_file_list()

    # ──────────────────────────────────────────
    # 按钮状态管理
    # ──────────────────────────────────────────
    def _set_idle_state(self):
        self.record_btn.set_sensitive(True)
        self.pause_btn.set_sensitive(False)
        self.pause_btn.set_label("暂停")
        self.pause_btn.set_icon_name("media-playback-pause-symbolic")
        self.stop_btn.set_sensitive(False)
        self.recording_hint.set_visible(False)

    def _set_recording_state(self, filename):
        self.record_btn.set_sensitive(False)
        self.pause_btn.set_sensitive(True)
        self.pause_btn.set_label("暂停")
        self.pause_btn.set_icon_name("media-playback-pause-symbolic")
        self.stop_btn.set_sensitive(True)
        self.recording_hint.set_label(f"● 录音中  {filename}")
        self.recording_hint.set_visible(True)

    def _set_paused_state(self, filename):
        self.pause_btn.set_label("继续")
        self.pause_btn.set_icon_name("media-playback-start-symbolic")
        self.recording_hint.set_label(f"⏸ 已暂停  {filename}")

    # ──────────────────────────────────────────
    # 录音
    # ──────────────────────────────────────────
    def on_record(self, btn):
        sink_info = find_recording_sink()
        if sink_info is None:
            self._toast("找不到音频输出设备")
            return

        sink_id, fmt, rate = sink_info
        device = f"{sink_id}.monitor"
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_name = f"系统录音_{ts}.wav"
        # 为每条录音创建独立文件夹
        folder_name = out_name.replace(".wav", "")
        rec_dir = os.path.join(str(self.output_dir), folder_name)
        os.makedirs(rec_dir, exist_ok=True)
        out_path = os.path.join(rec_dir, out_name)

        try:
            proc = subprocess.Popen(
                [
                    "parecord",
                    "--device", device,
                    "--channels", "2",
                    "--format", fmt,
                    "--rate", rate,
                    out_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self._toast("未找到 parecord，请安装 pulseaudio-utils")
            return
        except Exception as e:
            self._toast(f"启动录音失败: {e}")
            return

        self.recording_process = proc
        self.recording_path = out_path
        self.recording_paused = False
        self._set_recording_state(out_name)
        self._toast("开始录音")

    # ──────────────────────────────────────────
    # 暂停 / 继续录音
    # ──────────────────────────────────────────
    def on_pause(self, btn):
        if self.recording_process is None:
            return
        proc = self.recording_process
        name = os.path.basename(self.recording_path) if self.recording_path else ""

        if self.recording_paused:
            proc.send_signal(signal.SIGCONT)
            self.recording_paused = False
            self._set_recording_state(name)
            self._toast("继续录制")
        else:
            proc.send_signal(signal.SIGSTOP)
            self.recording_paused = True
            self._set_paused_state(name)
            self._toast("录制已暂停")

    # ──────────────────────────────────────────
    # 终止录音
    # ──────────────────────────────────────────
    def on_stop(self, btn):
        if self.recording_process is None:
            return

        proc = self.recording_process
        self.recording_process = None

        if self.recording_paused:
            proc.send_signal(signal.SIGCONT)
            self.recording_paused = False

        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        name = os.path.basename(self.recording_path) if self.recording_path else ""
        self._set_idle_state()
        self.statusbar.set_label(f"已保存: {name}")
        self.statusbar.add_css_class("dim-label")
        self.recording_path = None
        self._refresh_file_list()
        self._toast("录音已保存")

    # ──────────────────────────────────────────
    # 选择输出路径
    # ──────────────────────────────────────────
    def on_select_output(self, btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("选择输出目录")
        dialog.set_initial_folder(Gio.File.new_for_path(str(self.output_dir)))
        dialog.select_folder(
            parent=btn.get_root(),
            cancellable=None,
            callback=self._on_folder_selected,
        )

    def _on_folder_selected(self, dialog, result):
        try:
            gfile = dialog.select_folder_finish(result)
            if gfile:
                self.output_dir = Path(gfile.get_path())
                self.path_label.set_label(str(self.output_dir))
                self.path_label.set_tooltip_text(str(self.output_dir))
                self._refresh_file_list()
        except GLib.GError:
            pass

    def _on_open_folder(self, btn):
        """在系统文件管理器中打开输出目录。"""
        subprocess.Popen(["xdg-open", str(self.output_dir)],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

    # ──────────────────────────────────────────
    # 文件列表管理
    # ──────────────────────────────────────────
    def _get_recording_wavs(self):
        exclude = ("_vocals", "_play", "_mixed", "_segments")
        wavs = []
        # 扫描所有子目录中的原始录音
        for entry in os.listdir(str(self.output_dir)):
            subdir = os.path.join(str(self.output_dir), entry)
            if not os.path.isdir(subdir):
                continue
            for f in os.listdir(subdir):
                if not f.endswith(".wav"):
                    continue
                if any(x in f for x in exclude):
                    continue
                path = os.path.join(subdir, f)
                if os.path.isfile(path) and f not in self._hidden_set:
                    wavs.append(path)
        wavs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return wavs

    def _load_hidden(self) -> set:
        if self._hidden_file.is_file():
            try:
                with open(self._hidden_file, encoding="utf-8") as fh:
                    return {line.strip() for line in fh if line.strip()}
            except Exception:
                pass
        return set()

    def _save_hidden(self):
        try:
            with open(self._hidden_file, "w", encoding="utf-8") as fh:
                for name in sorted(self._hidden_set):
                    fh.write(name + "\n")
        except Exception:
            pass

    def _refresh_file_list(self):
        """重新扫描目录并重建文件列表。同时清理已不存在的隐藏条目。"""
        # 收集所有子目录中的文件名
        all_files = set()
        for entry in os.listdir(str(self.output_dir)):
            subdir = os.path.join(str(self.output_dir), entry)
            if os.path.isdir(subdir):
                all_files.update(os.listdir(subdir))
        stale = [n for n in self._hidden_set if n not in all_files]
        if stale:
            self._hidden_set.difference_update(stale)
            self._save_hidden()

        while row := self.file_list.get_first_child():
            self.file_list.remove(row)

        self.rows.clear()
        wavs = self._get_recording_wavs()
        if not wavs:
            empty_label = Gtk.Label(
                label="暂无录音文件\n点击「录音」开始录制",
                justify=Gtk.Justification.CENTER,
                margin_top=24,
                margin_bottom=24,
            )
            empty_label.add_css_class("dim-label")
            self.file_list.append(empty_label)
            return

        for path in wavs:
            row = RecordingRow(
                path,
                on_process=self._on_process_file,
                on_hide=self._on_hide_row,
                on_delete=self._on_delete_row,
                app=self,
            )
            self.file_list.append(row)
            self.rows.append(row)

    # ──────────────────────────────────────────
    # 处理单个文件
    # ──────────────────────────────────────────
    def _on_process_file(self, row: RecordingRow):
        if self.recording_process is not None:
            self._toast("请先终止当前录音")
            return
        if self.active_row is not None:
            self._toast("正在处理中，请等待完成")
            return
        if row._processed:
            self._toast("该条目已处理完成")
            return

        self.active_row = row
        row.show_progress("准备中...", 0.0)
        self.statusbar.set_label(f"后台处理: {row.basename}")
        self.statusbar.remove_css_class("dim-label")

        t = threading.Thread(
            target=self._process_worker,
            args=(row.filepath,),
            daemon=True,
        )
        t.start()

    def _process_worker(self, audio_path):
        row = self.active_row
        try:
            paths = resolve_paths(audio_path)
            vocals_path = paths["vocals"]
            midi_path = paths["midi"]

            # Step 1: Demucs
            GLib.idle_add(row.show_progress, "Demucs 人声分离...", 0.0)
            result = subprocess.run(
                ["uv", "run", str(SCRIPT_DIR / "vocal_extract.py"), audio_path],
                capture_output=True, text=True, timeout=600,
                cwd=str(self.output_dir),
            )
            if result.returncode != 0:
                err = (result.stderr or "")[:200]
                GLib.idle_add(self._on_proc_done, row, f"Demucs 失败: {err}")
                return

            GLib.idle_add(row.show_progress, "Demucs 完成", 0.45)

            if not os.path.isfile(vocals_path):
                GLib.idle_add(self._on_proc_done, row, "错误: 人声文件未生成")
                return

            # Step 2: Basic Pitch → MIDI
            GLib.idle_add(row.show_progress, "Basic Pitch 音高分析 → MIDI...", 0.45)
            result = subprocess.run(
                ["uv", "run", str(SCRIPT_DIR / "pitch_basic.py"),
                 "--save-midi", "--vocal", vocals_path],
                capture_output=True, text=True, timeout=600,
                cwd=str(self.output_dir),
            )
            if result.returncode != 0:
                err = (result.stderr or "")[:200]
                GLib.idle_add(self._on_proc_done, row, f"Basic Pitch 失败: {err}")
                return

            if os.path.isfile(midi_path):
                msg = f"✅ {os.path.basename(midi_path)}"
            else:
                msg = "✅ 处理完成"
            GLib.idle_add(row.show_progress, msg, 1.0)
            GLib.idle_add(self._on_proc_done, row, msg)

        except subprocess.TimeoutExpired:
            GLib.idle_add(self._on_proc_done, row, "处理超时 (600s)")
        except Exception as e:
            GLib.idle_add(self._on_proc_done, row, f"处理出错: {e}")

    def _on_proc_done(self, row: RecordingRow, msg):
        if msg.startswith("✅"):
            row._mark_processed()
        else:
            row.hide_progress()
        self.active_row = None
        self.statusbar.set_label(msg)
        self.statusbar.add_css_class("dim-label")
        self._toast(msg)
        return False

    # ──────────────────────────────────────────
    # 隐藏 / 删除
    # ──────────────────────────────────────────
    def _on_hide_row(self, row: RecordingRow):
        if row is self.active_row:
            self._toast("该文件正在处理中，无法移除")
            return
        # 停止播放（如果正在播）
        if self._playing_row is row:
            row.stop_playback()
            self._playing_row = None
        self._hidden_set.add(row.basename)
        self._save_hidden()
        self.file_list.remove(row)
        self.rows.remove(row)
        self._toast("已从列表移除")

    def _on_delete_row(self, row: RecordingRow):
        if row is self.active_row:
            self._toast("该文件正在处理中，无法删除")
            return

        # 停止播放（如果正在播）
        if self._playing_row is row:
            row.stop_playback()
            self._playing_row = None

        # 删除整个录音文件夹
        rec_dir = os.path.dirname(row.filepath)
        try:
            shutil.rmtree(rec_dir)
            deleted = 1
        except Exception:
            deleted = 0

        self.file_list.remove(row)
        self.rows.remove(row)
        self._hidden_set.discard(row.basename)
        self._save_hidden()
        self._toast(f"已删除 {deleted} 个文件")

    # ──────────────────────────────────────────
    # Toast 通知
    # ──────────────────────────────────────────
    def _toast(self, msg):
        win = self.get_active_window()
        if win and hasattr(win, "add_toast"):
            toast = Adw.Toast.new(msg)
            toast.set_timeout(3)
            win.add_toast(toast)


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = RecorderApp()
    app.run(sys.argv)