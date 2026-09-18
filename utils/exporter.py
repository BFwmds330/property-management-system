# -*- coding: utf-8 -*-
"""CSV / 文本导出工具（utf-8-sig 编码，Excel 可直接打开不乱码）。"""
import csv
import os
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _export_dir():
    d = os.path.join(_ROOT, 'data', 'exports')
    os.makedirs(d, exist_ok=True)
    return d


def export_csv(stem, headers, rows):
    """导出 CSV 到 data/exports/，返回文件完整路径。"""
    path = os.path.join(_export_dir(), f'{stem}_{datetime.now():%Y%m%d_%H%M%S}.csv')
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow(['' if c is None else c for c in r])
    return path


def export_text(stem, content):
    """导出文本（如催缴短信）到 data/exports/，返回文件完整路径。"""
    path = os.path.join(_export_dir(), f'{stem}_{datetime.now():%Y%m%d_%H%M%S}.txt')
    with open(path, 'w', encoding='utf-8-sig') as f:
        f.write(content)
    return path
