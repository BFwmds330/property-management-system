# -*- coding: utf-8 -*-
"""交互层公共组件：表格打印、房屋/楼栋/收费项目选择器。"""
from services import building_service, fee_service, house_service
from utils import tables
from utils.inputs import ask_int, ask_str


def print_table(headers, rows, aligns=None):
    print(tables.render(headers, rows, aligns))


def pick_house(ctx, prompt='请选择房屋'):
    """按关键字（房号/楼栋/业主姓名/手机号）检索并选择一套房屋，取消返回 None。"""
    kw = ask_str(f'{prompt}：输入房号/楼栋/业主姓名关键字（留空显示前 50 套）')
    rows = house_service.search(ctx.conn, ctx.community_id, kw, limit=50)
    if not rows:
        print('  ! 未找到匹配的房屋。')
        return None
    data = [[i + 1, house_service.code_of(r), house_service.label_of(r),
             f'{r["area_gross"]:.2f}㎡', r['status'], r['tname'] or '-',
             r['owner_name'] or '-', f'{r["arrears"] / 100:.2f}' if r['arrears'] else '-']
            for i, r in enumerate(rows)]
    print_table(['序号', '房号编码', '位置', '建筑面积', '状态', '户型', '业主', '欠费(元)'], data,
                ['l', 'l', 'l', 'r', 'l', 'l', 'l', 'r'])
    idx = ask_int('请输入序号选择房屋', minv=0, maxv=len(rows), default=0)
    return rows[idx - 1] if idx else None


def pick_building(ctx, prompt='请选择楼栋'):
    rows = building_service.list_with_count(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 当前小区还没有楼栋，请先在"楼栋管理"中新增。')
        return None
    data = [[i + 1, r['code'], r['unit_count'], r['floors'],
             '有' if r['has_elevator'] else '无', r['delivery_status'], r['house_count']]
            for i, r in enumerate(rows)]
    print_table(['序号', '楼栋编号', '单元数', '地上层数', '电梯', '交付状态', '房屋数'], data,
                ['l', 'l', 'r', 'r', 'l', 'l', 'r'])
    idx = ask_int('请输入序号选择楼栋', minv=0, maxv=len(rows), default=0)
    return rows[idx - 1] if idx else None


def pick_fee_item(ctx, prompt='请选择收费项目', enabled_only=False):
    rows = fee_service.items(ctx.conn, ctx.community_id, enabled_only=enabled_only)
    if not rows:
        print('  ! 当前小区还没有收费项目，请先在"收费项目配置"中新增。')
        return None
    data = [[i + 1, r['name'], r['pricing_type'], fee_service.item_price_text(r),
             r['period_type'], '启用' if r['enabled'] else '停用']
            for i, r in enumerate(rows)]
    print_table(['序号', '项目名称', '计价方式', '计价标准', '计费周期', '状态'], data)
    idx = ask_int('请输入序号选择收费项目', minv=0, maxv=len(rows), default=0)
    return rows[idx - 1] if idx else None
