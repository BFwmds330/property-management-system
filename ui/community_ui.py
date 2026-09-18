# -*- coding: utf-8 -*-
"""小区管理界面：新增/修改/删除/查询/汇总列表/切换当前小区。"""
from context import AppContext  # noqa: F401  (仅类型提示用途)
from services import community_service, log_service
from ui import menu
from ui.common_ui import print_table
from utils import colors, tables
from utils.inputs import (CancelInput, ask_date, ask_float, ask_int, ask_str,
                          confirm)


def _form(default=None):
    """小区信息表单。default 为已有记录时按项回填。"""
    d = default or {}
    return dict(
        name=ask_str('小区名称（唯一）', required=True, default=d.get('name')),
        address=ask_str('详细地址', default=d.get('address')),
        area_land=ask_float('占地面积（㎡）', minv=0, default=d.get('area_land') or None,
                            required=False) or 0,
        area_building=ask_float('总建筑面积（㎡）', minv=0, default=d.get('area_building') or None,
                                required=False) or 0,
        green_rate=ask_float('绿化率（%）', minv=0, maxv=100, default=d.get('green_rate') or None,
                             required=False) or 0,
        plan_buildings=ask_int('规划楼栋数量', minv=0, required=False,
                               default=d.get('plan_buildings') or None) or 0,
        parking_total=ask_int('车位总数', minv=0, required=False,
                              default=d.get('parking_total') or None) or 0,
        delivery_date=ask_date('房屋交付日期', default=d.get('delivery_date') or None),
        takeover_date=ask_date('物业接管日期', default=d.get('takeover_date') or None),
        service_phone=ask_str('物业服务处电话', max_len=20, default=d.get('service_phone') or None),
        remark=ask_str('备注', default=d.get('remark')),
    )


def add_ui(ctx):
    try:
        data = _form()
    except CancelInput:
        print('  已取消新增。')
        return
    cid = community_service.create(ctx.conn, data)
    print(colors.green(f'  [成功] 小区「{data["name"]}」已创建（编号 {cid}）。'))
    if not ctx.community_id and confirm('是否将其设为当前小区？', default=True):
        ctx.set_community(community_service.get(ctx.conn, cid))


def edit_ui(ctx):
    rows = community_service.list_stats(ctx.conn)
    if not rows:
        print('  ! 暂无小区，请先新增。')
        return
    _list_table(rows, ctx.community_id)
    cid = ask_int('请输入要修改的小区编号（community.id，0 取消）', minv=0)
    if not cid:
        return
    row = community_service.get(ctx.conn, cid)
    if not row:
        raise ValueError('小区编号不存在')
    try:
        data = _form(default=dict(row))
    except CancelInput:
        print('  已取消修改。')
        return
    community_service.update(ctx.conn, cid, data)
    ctx.refresh_name(cid, data['name'])
    print(colors.green(f'  [成功] 小区「{data["name"]}」信息已更新。'))


def delete_ui(ctx):
    rows = community_service.list_stats(ctx.conn)
    if not rows:
        print('  ! 暂无小区。')
        return
    _list_table(rows, ctx.community_id)
    cid = ask_int('请输入要删除的小区编号（community.id，0 取消）', minv=0)
    if not cid:
        return
    row = community_service.get(ctx.conn, cid)
    if not row:
        raise ValueError('小区编号不存在')
    print(colors.red('  !! 危险操作：将级联删除该小区下所有楼栋、房屋、住户关系、账单数据，且不可恢复！'))
    if confirm(f'确认删除小区「{row["name"]}」？', default=False):
        name = community_service.delete(ctx.conn, cid)
        log_service.add(ctx.conn, None, '删除小区', f'「{name}」及其全部下级数据已删除')
        if ctx.community_id == cid:
            ctx.community_id = None
            ctx.community_name = None
        print(colors.green(f'  [成功] 小区「{name}」及其全部数据已删除。'))
    else:
        print('  已取消删除。')


def search_ui(ctx):
    kw = ask_str('输入小区名称/地址关键字', required=True)
    rows = community_service.search(ctx.conn, kw)
    if not rows:
        print('  ! 未找到匹配的小区。')
        return
    stats = {r['id']: r for r in community_service.list_stats(ctx.conn)}
    data = [[r['id'], r['name'], r['address'],
             stats[r['id']]['building_count'], stats[r['id']]['house_count'],
             stats[r['id']]['resident_count'], tables.money(stats[r['id']]['arrears'])]
            for r in rows]
    print_table(['编号', '名称', '地址', '楼栋数', '房屋数', '在住人数', '欠费总额(元)'], data,
                ['l', 'l', 'l', 'r', 'r', 'r', 'r'])


def list_ui(ctx):
    rows = community_service.list_stats(ctx.conn)
    if not rows:
        print('  ! 暂无小区，请先新增。')
        return
    _list_table(rows, ctx.community_id)


def _list_table(rows, current_id):
    data = []
    for r in rows:
        mark = '*' if r['id'] == current_id else ''
        data.append([f'{mark}{r["id"]}', r['name'], r['address'] or '-', r['building_count'],
                     r['house_count'], r['resident_count'], tables.money(r['arrears'])])
    print_table(['编号', '小区名称', '地址', '楼栋数', '房屋数', '在住人数', '欠费总额(元)'], data,
                ['l', 'l', 'l', 'r', 'r', 'r', 'r'])
    if current_id:
        print('（带 * 号为当前小区）')


def switch_ui(ctx):
    rows = community_service.list_stats(ctx.conn)
    if not rows:
        print('  ! 暂无小区，请先新增。')
        return False
    _list_table(rows, ctx.community_id)
    cid = ask_int('请输入要切换到的小区编号（0 取消）', minv=0)
    if not cid:
        print('  已取消切换。')
        return False
    row = community_service.get(ctx.conn, cid)
    if not row:
        raise ValueError('小区编号不存在')
    ctx.set_community(row)
    print(colors.green(f'  [成功] 当前小区已切换为「{row["name"]}」，后续操作均针对该小区。'))
    return True


def run(ctx):
    menu.run_menu(ctx, '小区管理', [
        ('1', '新增小区', add_ui),
        ('2', '修改小区信息', edit_ui),
        ('3', '删除小区', delete_ui),
        ('4', '查询小区（名称/地址模糊）', search_ui),
        ('5', '小区汇总列表', list_ui),
        ('6', '切换当前小区', switch_ui),
    ])
    return True
