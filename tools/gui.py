# /// script
# dependencies = []
# ///

"""
录音分析 GUI — GNOME 风格 (GTK4 + Adwaita)

使用:
    python3 gui.py

依赖系统包: gtk4, libadwaita, python3-gobject, pulseaudio-utils
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
import subprocess
import os
import sys
import signal
import threading
import time
import math
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()


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
# 查找音频 Sink
# ──────────────────────────────────────────────
def find_recording_sink():
    """返回 (sink_id, format, rate) 或 None。"""
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sinks", "short"],
            text=True, stderr=subprocess.DEVNULL,
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
            text=True, stderr=subprocess.DEVNULL,
        )
        fmt = "s16le"
        rate = "48000"
        in_target = False
        for line in long_out.split("\n"):
            m_id = re.match(r"(?:信宿|Sink)\s+#(\d+)", line)
            if m_id:
                in_target = (m_id.group(1) == sink_id)
                continue
            if not in_target:
                continue
            m_spec = re.search(
                r"(?:采样规格|Sample\s+Specification)[：:]\s*(.+)", line,
            )
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
    """文件列表中的一行：文件名 + 播放 / 处理 / 隐藏 / 删除 + 内嵌进度条。"""

    def __init__(self, filepath, on_play, on_process, on_hide, on_delete):
        super().__init__()
        self.filepath = filepath
        self.basename = os.path.basename(filepath)

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

        # 播放录音
        play_btn = Gtk.Button(label="播放")
        play_btn.set_icon_name("media-playback-start-symbolic")
        play_btn.add_css_class("flat")
        play_btn.add_css_class("compact")
        play_btn.set_tooltip_text("播放原始录音")
        play_btn.connect("clicked", lambda b: on_play(self.filepath))
        row.append(play_btn)

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

        # ── 进度区域 (Revealer 展开) ──
        self.progress_revealer = Gtk.Revealer()
        self.progress_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_DOWN
        )
        self.progress_revealer.set_transition_duration(200)

        progress_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4,
        )
        progress_box.set_margin_start(36)
        progress_box.set_margin_end(12)
        progress_box.set_margin_bottom(6)

        self.progress_label = Gtk.Label(label="", xalign=0)
        self.progress_label.add_css_class("caption")
        progress_box.append(self.progress_label)

        self.progress_bar = Gtk.ProgressBar(hexpand=True)
        progress_box.append(self.progress_bar)

        self.progress_revealer.set_child(progress_box)
        outer.append(self.progress_revealer)

        self.set_child(outer)

    # ── 进度 UI ──
    def show_progress(self, text, fraction):
        self.process_btn.set_sensitive(False)
        self.progress_revealer.set_reveal_child(True)
        self.progress_label.set_label(text)
        self.progress_bar.set_fraction(fraction)

    def hide_progress(self):
        self.process_btn.set_sensitive(True)
        self.progress_revealer.set_reveal_child(False)


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
        self.active_row: RecordingRow | None = None  # 正在处理的
        self._hidden_file = self.output_dir / ".hidden_recordings"
        self._hidden_set: set[str] = self._load_hidden()

    def do_activate(self):
        win = Adw.ApplicationWindow(application=self)
        win.set_default_size(580, 680)
        win.set_title("录音分析工具")
        win.set_resizable(True)

        # ── 工具箱 (含 HeaderBar + 内容) ──
        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_title(True)
        toolbar_view.add_top_bar(header)

        # ── 外层滚动容器 ──
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        # ── 主布局 ──
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
        main_box.append(path_box)

        # ── 进度条 (录制时显示) ──
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

        # ── 文件列表标头 ──
        list_header = Gtk.Label(label="录音文件", xalign=0)
        list_header.add_css_class("heading")
        main_box.append(list_header)

        # ── 文件列表 ──
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

        # 初始扫描文件列表
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
        out_path = os.path.join(str(self.output_dir), out_name)

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
    # 暂停 / 继续
    # ──────────────────────────────────────────
    def on_pause(self, btn):
        if self.recording_process is None:
            return
        proc = self.recording_process
        name = os.path.basename(self.recording_path) if self.recording_path else ""

        if self.recording_paused:
            # 继续录制
            proc.send_signal(signal.SIGCONT)
            self.recording_paused = False
            self._set_recording_state(name)
            self._toast("继续录制")
        else:
            # 暂停录制
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

        # 如果处于暂停状态，先 SIGCONT 让进程响应 SIGINT
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

    # ──────────────────────────────────────────
    # 文件列表管理
    # ──────────────────────────────────────────
    def _get_recording_wavs(self):
        """返回目录中的原始录音文件（排除生成文件和已隐藏文件）。"""
        exclude = ("_vocals", "_play", "_mixed", "_segments")
        wavs = []
        for f in os.listdir(str(self.output_dir)):
            if not f.endswith(".wav"):
                continue
            if any(x in f for x in exclude):
                continue
            path = os.path.join(str(self.output_dir), f)
            if os.path.isfile(path) and f not in self._hidden_set:
                wavs.append(path)
        wavs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return wavs

    def _load_hidden(self) -> set:
        """加载被隐藏的文件名集合。"""
        if self._hidden_file.is_file():
            try:
                with open(self._hidden_file, encoding="utf-8") as fh:
                    return {line.strip() for line in fh if line.strip()}
            except Exception:
                pass
        return set()

    def _save_hidden(self):
        """保存被隐藏的文件名集合。"""
        try:
            with open(self._hidden_file, "w", encoding="utf-8") as fh:
                for name in sorted(self._hidden_set):
                    fh.write(name + "\n")
        except Exception:
            pass

    def _refresh_file_list(self):
        """重新扫描目录并重建文件列表。同时清理已不存在的隐藏条目。"""
        # 清理隐藏列表中已删除的文件
        stale = [n for n in self._hidden_set
                 if not os.path.isfile(self.output_dir / n)]
        if stale:
            self._hidden_set.difference_update(stale)
            self._save_hidden()

        # 清空列表
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
                on_play=self._on_play_recording,
                on_process=self._on_process_file,
                on_hide=self._on_hide_row,
                on_delete=self._on_delete_row,
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
        """后台处理线程。"""
        row = self.active_row
        try:
            scripts_dir = SCRIPT_DIR
            base = os.path.splitext(audio_path)[0]
            vocals_path = f"{base}_vocals.wav"

            # Step 1: Demucs
            GLib.idle_add(row.show_progress, "Demucs 人声分离...", 0.0)
            result = subprocess.run(
                ["uv", "run", str(scripts_dir / "vocal_extract.py"), audio_path],
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
                ["uv", "run", str(scripts_dir / "pitch_basic.py"),
                 "--save-midi", "--vocal", vocals_path],
                capture_output=True, text=True, timeout=600,
                cwd=str(self.output_dir),
            )
            if result.returncode != 0:
                err = (result.stderr or "")[:200]
                GLib.idle_add(self._on_proc_done, row, f"Basic Pitch 失败: {err}")
                return

            # 完成
            midi_path = f"{vocals_path.replace('.wav', '')}_basic_pitch.mid"
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
        """处理完成/失败时清理"""
        row.hide_progress()
        self.active_row = None
        self.statusbar.set_label(msg)
        self.statusbar.add_css_class("dim-label")
        self._toast(msg)
        return False

    # ──────────────────────────────────────────
    # 播放录音
    # ──────────────────────────────────────────
    def _on_play_recording(self, filepath):
        if not os.path.isfile(filepath):
            self._toast("录音文件不存在")
            return
        try:
            subprocess.Popen(["paplay", filepath])
            self._toast("正在播放...")
        except FileNotFoundError:
            self._toast("未找到 paplay")
        except Exception as e:
            self._toast(f"播放失败: {e}")

    # ──────────────────────────────────────────
    # 删除条目 / 删除文件
    # ──────────────────────────────────────────
    def _on_hide_row(self, row: RecordingRow):
        """从列表中移除条目（保留文件，下次刷新不再显示）。"""
        if row is self.active_row:
            self._toast("该文件正在处理中，无法移除")
            return
        self._hidden_set.add(row.basename)
        self._save_hidden()
        self.file_list.remove(row)
        self.rows.remove(row)
        self._toast("已从列表移除")

    def _on_delete_row(self, row: RecordingRow):
        """删除文件及所有关联的生成文件。"""
        if row is self.active_row:
            self._toast("该文件正在处理中，无法删除")
            return

        base = os.path.splitext(row.filepath)[0]
        patterns = [
            row.filepath,                          # 原始录音
            f"{base}_vocals.wav",                  # 人声
            f"{base}_vocals_basic_pitch.mid",      # MIDI
            f"{base}_vocals_segments.csv",         # 音段
            f"{base}_vocals_play.wav",             # 纯音
            f"{base}_vocals_mixed.wav",            # 混合
            f"{base}_vocals_pitch.csv",            # 人声音高
            f"{base}_vocals_pitch.png",            # 人声音高图
            f"{base}_pitch.csv",                   # 原始音高
            f"{base}_pitch.png",                   # 原始音高图
            f"{base}_segments.csv",                # 原始音段
            f"{base}_basic_pitch.mid",             # 原始 MIDI
            f"{base}_full.mid",                    # 完整 MIDI
        ]

        deleted = 0
        for p in patterns:
            if os.path.isfile(p):
                os.remove(p)
                deleted += 1

        self.file_list.remove(row)
        self.rows.remove(row)
        # 清理隐藏记录（文件已物理删除，无需再隐藏）
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