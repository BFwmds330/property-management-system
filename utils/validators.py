# -*- coding: utf-8 -*-
"""数据校验工具：所有校验函数返回 (是否通过, 规范化值或中文错误提示)。"""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

_PHONE_RE = re.compile(r'^1[3-9]\d{9}$')
_ID_RE = re.compile(r'^\d{17}[0-9X]$', re.IGNORECASE)
# 18 位身份证校验位算法（GB 11643-1999）
_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK = '10X98765432'


def check_phone(v):
    """手机号：1 开头的 11 位数字。"""
    v = (v or '').strip()
    if not v:
        return False, '手机号不能为空'
    if not _PHONE_RE.match(v):
        return False, '手机号格式不正确，应为 1 开头的 11 位数字（如 13812345678）'
    return True, v


def check_id_card(v):
    """18 位身份证号（含出生日期合法性与校验位验证）。"""
    v = (v or '').strip().upper()
    if not v:
        return False, '证件号不能为空'
    if not _ID_RE.match(v):
        return False, '身份证号应为 18 位（前 17 位数字，末位为数字或 X）'
    try:
        datetime.strptime(v[6:14], '%Y%m%d')
    except ValueError:
        return False, '身份证号中的出生日期段不合法，请核对'
    s = sum(int(v[i]) * _ID_WEIGHTS[i] for i in range(17))
    if _ID_CHECK[s % 11] != v[17]:
        return False, '身份证校验位不正确，请核对号码是否输入有误'
    return True, v


def check_general_id(v):
    """非身份证证件号：仅要求非空、长度合理。"""
    v = (v or '').strip()
    if not v:
        return False, '证件号不能为空'
    if len(v) > 30:
        return False, '证件号过长（不超过 30 位）'
    return True, v


def check_date(v):
    """日期：YYYY-MM-DD，且必须是真实存在的日期。"""
    v = (v or '').strip()
    try:
        d = datetime.strptime(v, '%Y-%m-%d')
    except ValueError:
        return False, '日期格式应为 YYYY-MM-DD（如 2026-09-01）'
    if not (1900 <= d.year <= 2100):
        return False, '日期年份应在 1900-2100 之间'
    return True, v


def check_period(v, period_type='月'):
    """账期：按计费周期校验（月 YYYY-MM / 季 YYYY-Qn / 年 YYYY）。"""
    v = (v or '').strip().upper()
    if period_type == '月':
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', v):
            return False, '账期格式应为 YYYY-MM（如 2026-09）'
        return True, v
    if period_type == '季':
        if not re.match(r'^\d{4}-Q[1-4]$', v):
            return False, '账期格式应为 YYYY-Qn（如 2026-Q3，n 取 1-4）'
        return True, v
    if not re.match(r'^\d{4}$', v):
        return False, '账期格式应为 YYYY（如 2026）'
    if not (1990 <= int(v) <= 2100):
        return False, '账期年份应在 1990-2100 之间'
    return True, v


def check_int(v, minv=None, maxv=None):
    """整数（可限定范围）。"""
    v = (v or '').strip()
    try:
        n = int(v)
    except (TypeError, ValueError):
        return False, '请输入整数'
    if minv is not None and n < minv:
        return False, f'数值不能小于 {minv}'
    if maxv is not None and n > maxv:
        return False, f'数值不能大于 {maxv}'
    return True, n


def check_float(v, minv=None, maxv=None):
    """小数（面积、绿化率等，最多两位小数）。"""
    v = (v or '').strip()
    try:
        d = Decimal(v)
    except (InvalidOperation, TypeError, ValueError):
        return False, '请输入数字（如 78 或 118.50）'
    if -d.as_tuple().exponent > 2:
        return False, '最多保留两位小数'
    if minv is not None and d < minv:
        return False, f'数值不能小于 {minv}'
    if maxv is not None and d > maxv:
        return False, f'数值不能大于 {maxv}'
    return True, float(d)


def check_money(v, allow_zero=True):
    """金额（元）转"分"整数存储，避免浮点误差。"""
    v = (v or '').strip().replace('￥', '').replace('元', '')
    if v == '':
        return False, '金额不能为空'
    try:
        d = Decimal(v)
    except InvalidOperation:
        return False, '金额格式不正确，请输入数字（如 350 或 350.50）'
    if d < 0:
        return False, '金额不能为负数'
    if -d.as_tuple().exponent > 2:
        return False, '金额最多保留两位小数'
    cents = int((d * 100).quantize(Decimal('1')))
    if not allow_zero and cents == 0:
        return False, '金额不能为 0'
    return True, cents


def id_card_birth(v):
    """从合法身份证号中提取出生日期（YYYY-MM-DD），不合法返回空串。"""
    v = (v or '').strip()
    if _ID_RE.match(v):
        try:
            return datetime.strptime(v[6:14], '%Y%m%d').strftime('%Y-%m-%d')
        except ValueError:
            pass
    return ''
