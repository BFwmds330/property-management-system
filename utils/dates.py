# -*- coding: utf-8 -*-
"""日期与账期工具。"""
import calendar
from datetime import date, datetime


def today_str():
    return date.today().isoformat()


def month_last_day(period):
    """'2026-09' -> '2026-09-30'。"""
    y, m = int(period[:4]), int(period[5:7])
    return f'{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}'


def quarter_last_day(period):
    """'2026-Q3' -> '2026-09-30'。"""
    y, q = int(period[:4]), int(period[-1])
    m = q * 3
    return f'{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}'


def period_due(period_type, period):
    """账单最迟缴纳日期：取计费周期期末日。"""
    if period_type == '季':
        return quarter_last_day(period)
    if period_type == '年':
        return f'{int(period[:4]):04d}-12-31'
    return month_last_day(period)


def days_since(day_str):
    """距今多少天（过去为正数，未来或非法为 0）。"""
    try:
        d = datetime.strptime(day_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return 0
    return max(0, (date.today() - d).days)


def days_until(day_str):
    """距某日还有多少天（已过期返回负数；非法返回 None）。"""
    try:
        d = datetime.strptime(day_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None
    return (d - date.today()).days
