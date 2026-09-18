# -*- coding: utf-8 -*-
"""交互输入助手：统一处理输入、校验、重试与取消。

约定：在任何输入提示中键入 q（回车确认）即可取消当前操作，表单代码通过
捕获 CancelInput 异常统一返回上级，任何非法输入都只提示重试、不会崩溃。
"""
from utils import validators


class CancelInput(Exception):
    """用户输入 q 主动取消当前操作。"""


def _read(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise CancelInput('输入已中断')


def ask_str(prompt, *, required=False, default=None, max_len=100):
    """单行文本。default 非空时回车取默认值；required 时空输入重试。"""
    tip = f'（回车={default}，q 取消）' if default else (
        '（必填，q 取消）' if required else '（可留空，q 取消）')
    while True:
        s = _read(f'{prompt}{tip}：')
        if s.lower() == 'q':
            raise CancelInput()
        if not s:
            if default:
                return str(default)
            if not required:
                return ''
            print('  × 该项为必填，请重新输入。')
            continue
        if len(s) > max_len:
            print(f'  × 输入过长（最多 {max_len} 个字符），请重新输入。')
            continue
        return s


def ask_int(prompt, *, minv=None, maxv=None, default=None, required=True):
    """整数。required=False 时空输入返回 None（可选项）。"""
    tip = f'（回车={default}，q 取消）' if default is not None else (
        '（必填，q 取消）' if required else '（可留空，q 取消）')
    rng = ''
    if minv is not None and maxv is not None:
        rng = f'，范围 {minv}-{maxv}'
    elif minv is not None:
        rng = f'，不小于 {minv}'
    elif maxv is not None:
        rng = f'，不大于 {maxv}'
    while True:
        s = _read(f'{prompt}{tip}：')
        if s.lower() == 'q':
            raise CancelInput()
        if not s:
            if default is not None:
                return default
            if not required:
                return None
            print('  × 该项为必填，请重新输入。')
            continue
        ok, v = validators.check_int(s, minv, maxv)
        if ok:
            return v
        print(f'  × {v}{rng}。')


def ask_float(prompt, *, minv=None, maxv=None, default=None, required=True):
    """小数（面积/绿化率等）。required=False 时空输入返回 None。"""
    tip = f'（回车={default}，q 取消）' if default is not None else (
        '（必填，q 取消）' if required else '（可留空，q 取消）')
    while True:
        s = _read(f'{prompt}{tip}：')
        if s.lower() == 'q':
            raise CancelInput()
        if not s:
            if default is not None:
                return float(default)
            if not required:
                return None
            print('  × 该项为必填，请重新输入。')
            continue
        ok, v = validators.check_float(s, minv, maxv)
        if ok:
            return v
        print(f'  × {v}。')


def ask_money(prompt, *, default=None, required=True, allow_zero=True):
    """金额（元），返回"分"整数。required=False 时空输入返回 None。"""
    tip = f'（元，回车={default}，q 取消）' if default is not None else (
        '（元，必填，q 取消）' if required else '（元，可留空，q 取消）')
    while True:
        s = _read(f'{prompt}{tip}：')
        if s.lower() == 'q':
            raise CancelInput()
        if not s:
            if default is not None:
                ok, cents = validators.check_money(str(default), allow_zero=True)
                return cents
            if not required:
                return None
            print('  × 金额不能为空。')
            continue
        ok, cents = validators.check_money(s, allow_zero=allow_zero)
        if ok:
            return cents
        print(f'  × {cents}。')


def ask_date(prompt, *, default=None, required=False):
    """日期 YYYY-MM-DD。"""
    tip = f'（YYYY-MM-DD，回车={default}，q 取消）' if default else (
        '（YYYY-MM-DD，必填，q 取消）' if required else '（YYYY-MM-DD，可留空，q 取消）')
    while True:
        s = _read(f'{prompt}{tip}：')
        if s.lower() == 'q':
            raise CancelInput()
        if not s:
            if default:
                return default
            if not required:
                return ''
            print('  × 日期不能为空。')
            continue
        ok, v = validators.check_date(s)
        if ok:
            return v
        print(f'  × {v}。')


def ask_period(prompt, period_type, *, default=None):
    """账期（按计费周期自动校验格式）。"""
    tip = f'（回车={default}，q 取消）' if default else '（q 取消）'
    while True:
        s = _read(f'{prompt}{tip}：')
        if s.lower() == 'q':
            raise CancelInput()
        if not s and default:
            return default
        ok, v = validators.check_period(s, period_type)
        if ok:
            return v
        print(f'  × {v}。')


def ask_choice(prompt, options, *, default=None):
    """单选。options: [(key, label), ...]，返回所选 key。"""
    keys = [k for k, _ in options]
    inline = '  '.join(f'{k}={label}' for k, label in options)
    tip = f'（回车={default}，q 取消）' if default else '（q 取消）'
    while True:
        s = _read(f'{prompt}（{inline}）{tip}：')
        if s.lower() == 'q':
            raise CancelInput()
        if not s and default is not None:
            return default
        if s in keys:
            return s
        print('  × 无效选项，请重新输入。')


def confirm(prompt, default=False):
    """是/否确认（危险操作请保持默认 False）。"""
    tip = '（y=是，n=否，回车=%s，q 取消）' % ('y' if default else 'n')
    while True:
        s = _read(f'{prompt}{tip}：')
        if s == '':
            return bool(default)
        if s.lower() in ('y', 'yes', '是'):
            return True
        if s.lower() in ('n', 'no', '否', 'q'):
            return False
        print('  × 请输入 y 或 n。')


def pause():
    """动作结束后暂停，便于查看输出。"""
    try:
        input('\n按回车键继续...')
    except (EOFError, KeyboardInterrupt):
        pass
