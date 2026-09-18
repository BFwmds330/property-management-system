# -*- coding: utf-8 -*-
"""终端颜色输出（仅标准库；在支持的终端自动启用 ANSI，重定向输出时自动关闭）。"""
import os
import sys

_enabled = False


def enable():
    """在交互式终端上启用 ANSI 颜色（Windows 10+ 通过 os.system('') 开启支持）。"""
    global _enabled
    try:
        if sys.stdout.isatty():
            if os.name == 'nt':
                os.system('')
            _enabled = True
    except Exception:
        _enabled = False


def _wrap(text, code):
    if _enabled:
        return f'\033[{code}m{text}\033[0m'
    return text


def red(t):
    return _wrap(t, '31')


def green(t):
    return _wrap(t, '32')


def yellow(t):
    return _wrap(t, '33')


def cyan(t):
    return _wrap(t, '36')


def bold(t):
    return _wrap(t, '1')
