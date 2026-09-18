# -*- coding: utf-8 -*-
"""纯标准库表格渲染：按中文全角字符宽度对齐，不依赖第三方库。"""
import unicodedata


def _width(s):
    return sum(2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1 for ch in s)


def _pad(s, w, align='l'):
    gap = w - _width(s)
    if gap <= 0:
        return s
    return s + ' ' * gap if align == 'l' else ' ' * gap + s


def render(headers, rows, aligns=None):
    """渲染表格字符串。

    headers: 表头列表；rows: 二维列表（非字符串会自动 str()，None 视为空）；
    aligns: 每列 'l'/'r' 对齐（默认全左对齐）。
    """
    n = len(headers)
    aligns = aligns or ['l'] * n
    cells = [[('' if c is None else str(c)) for c in r] for r in rows]
    widths = [_width(h) for h in headers]
    for r in cells:
        for i in range(n):
            widths[i] = max(widths[i], _width(r[i] if i < len(r) else ''))

    def line(ch):
        return '+' + '+'.join(ch * (w + 2) for w in widths) + '+'

    def fmt(row, aligns_):
        parts = []
        for i in range(n):
            v = row[i] if i < len(row) else ''
            parts.append(' ' + _pad(v, widths[i], aligns_[i]) + ' ')
        return '|' + '|'.join(parts) + '|'

    out = [line('-'), fmt(headers, ['l'] * n), line('=')]
    for r in cells:
        out.append(fmt(r, aligns))
    out.append(line('-'))
    return '\n'.join(out)


def money(cents):
    """分 -> '1,234.56' 元字符串（整数运算，无浮点误差）。"""
    if cents is None:
        cents = 0
    cents = int(cents)
    sign = '-' if cents < 0 else ''
    cents = abs(cents)
    return f'{sign}{cents // 100:,}.{cents % 100:02d}'


def rate_text(receivable, received):
    """收缴率文本；应收为 0 时显示 '-'。"""
    if not receivable:
        return '-'
    return f'{received / receivable * 100:.2f}%'
