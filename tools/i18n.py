# /// script
# dependencies = []
# ///

"""国际化模块 — 基于 JSON 翻译文件的语言切换。

语言检测优先级：
  1. 环境变量 NOTECATCH_LANG（如 NOTECATCH_LANG=en）
  2. 系统 locale（zh_* → zh，其他 → en）

用法:
    from i18n import _, set_lang, get_lang
    label = _("播放")           # 自动根据当前语言翻译
    set_lang("en")              # 手动切换语言

添加新语言：
    在 tools/locales/ 目录下创建 <lang>.json 文件即可。
"""

import json
import locale
import os
from pathlib import Path

_locales_dir = Path(__file__).parent / "locales"
_current_lang: str | None = None
_translations: dict[str, dict[str, str]] = {}


def _detect_lang() -> str:
    """检测系统语言，返回语言代码。"""
    env = os.environ.get("NOTECATCH_LANG", "")
    if env:
        return env
    try:
        lang, _ = locale.getlocale()
        if lang and lang.startswith("zh"):
            return "zh"
    except Exception:
        pass
    return "en"


def get_lang() -> str:
    """获取当前语言代码。"""
    global _current_lang
    if _current_lang is None:
        _current_lang = _detect_lang()
    return _current_lang


def set_lang(lang: str) -> None:
    """手动设置语言（如 'zh', 'en'）。"""
    global _current_lang
    _current_lang = lang


def _(text: str) -> str:
    """翻译字符串。未找到翻译时返回原文。"""
    lang = get_lang()
    if lang not in _translations:
        _load_translations(lang)
    return _translations.get(lang, {}).get(text, text)


def _load_translations(lang: str) -> None:
    """加载指定语言的 JSON 翻译文件。"""
    path = _locales_dir / f"{lang}.json"
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                _translations[lang] = json.load(f)
        except (json.JSONDecodeError, OSError):
            _translations[lang] = {}
    else:
        _translations[lang] = {}
