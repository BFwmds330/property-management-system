# -*- coding: utf-8 -*-
"""统计报表界面：账期/年度收缴报表、欠费 Top 10、各小区收缴率对比，均支持导出 CSV。"""
from services import report_service
from ui import menu
from ui.common_ui import print_table
from utils import colors, tables
from utils import exporter
from utils.inputs import CancelInput, ask_str, confirm


def _period_rows(rows, recv, paid):
    data = [[r['item_name'], f'{r["recv"] / 100:.2f}', f'{r["paid"] / 100:.2f}',
             tables.rate_text(r['recv'], r['paid'])] for r in rows]
    data.append(['合计', f'{recv / 100:.2f}', f'{paid / 100:.2f}', tables.rate_text(recv, paid)])
    return data


def period_report_ui(ctx):
    try:
        period = ask_str('输入账期（如 2026-09 / 2026-Q3 / 2026，与账单账期一致）', required=True,
                         max_len=10)
    except CancelInput:
        print('  已取消。')
        return
    rows, recv, paid = report_service.period_summary(ctx.conn, ctx.community_id, period)
    if not rows:
        print('  ! 该账期暂无账单数据。')
        return
    print(f'  账期 {period} 收缴报表（当前小区：{ctx.community_name}）')
    print_table(['收费项目', '应收(元)', '实收(元)', '收缴率'], _period_rows(rows, recv, paid),
                ['l', 'r', 'r', 'r'])
    print('  ' + report_service.summary_text(recv, paid))
    if confirm('是否导出 CSV？', default=False):
        path = exporter.export_csv(f'账期报表_{ctx.community_name}_{period}',
                                   ['收费项目', '应收(元)', '实收(元)', '收缴率'],
                                   _period_rows(rows, recv, paid))
        print(colors.green(f'  [成功] 已导出 -> {path}'))


def year_report_ui(ctx):
    try:
        year = ask_str('输入年度（如 2026）', required=True, max_len=4)
    except CancelInput:
        print('  已取消。')
        return
    rows, recv, paid = report_service.year_summary(ctx.conn, ctx.community_id, year)
    if not rows:
        print('  ! 该年度暂无账单数据。')
        return
    print(f'  {year} 年度收缴报表（当前小区：{ctx.community_name}）')
    print_table(['收费项目', '应收(元)', '实收(元)', '收缴率'], _period_rows(rows, recv, paid),
                ['l', 'r', 'r', 'r'])
    print('  ' + report_service.summary_text(recv, paid))
    if confirm('是否导出 CSV？', default=False):
        path = exporter.export_csv(f'年度报表_{ctx.community_name}_{year}',
                                   ['收费项目', '应收(元)', '实收(元)', '收缴率'],
                                   _period_rows(rows, recv, paid))
        print(colors.green(f'  [成功] 已导出 -> {path}'))


def top_arrears_ui(ctx):
    rows = report_service.top_arrears(ctx.conn, ctx.community_id, 10)
    if not rows:
        print(colors.green('  当前小区没有欠费房源。'))
        return
    data = [[i + 1, f'{r["bcode"]} {r["unit"]}单元 {r["room_no"]}室', r['owner_name'] or '-',
             f'{r["balance"] / 100:.2f}', r['bill_count']] for i, r in enumerate(rows)]
    print_table(['名次', '房号', '业主', '欠费总额(元)', '欠费笔数'], data,
                ['l', 'l', 'l', 'r', 'r'])
    if confirm('是否导出 CSV？', default=False):
        path = exporter.export_csv(f'欠费Top10_{ctx.community_name}',
                                   ['名次', '房号', '业主', '欠费总额(元)', '欠费笔数'],
                                   [[c for c in row] for row in data])
        print(colors.green(f'  [成功] 已导出 -> {path}'))


def compare_ui(ctx):
    try:
        prefix = ask_str('输入账期或年度前缀（如 2026-09 或 2026）', required=True, max_len=10)
    except CancelInput:
        print('  已取消。')
        return
    rows = report_service.communities_summary(ctx.conn, prefix)
    data = [[r['name'], f'{r["recv"] / 100:.2f}', f'{r["paid"] / 100:.2f}',
             tables.rate_text(r['recv'], r['paid'])] for r in rows]
    print(f'  各小区收缴率对比（账期/年度：{prefix}）')
    print_table(['小区', '应收(元)', '实收(元)', '收缴率'], data, ['l', 'r', 'r', 'r'])
    if confirm('是否导出 CSV？', default=False):
        path = exporter.export_csv(f'各小区收缴率对比_{prefix}',
                                   ['小区', '应收(元)', '实收(元)', '收缴率'], data)
        print(colors.green(f'  [成功] 已导出 -> {path}'))


def run(ctx):
    menu.run_menu(ctx, '统计报表', [
        ('1', '账期收缴报表', period_report_ui),
        ('2', '年度收缴报表', year_report_ui),
        ('3', '欠费金额 Top 10', top_arrears_ui),
        ('4', '各小区收缴率对比', compare_ui),
    ])
    return True
