# -*- coding: utf-8 -*-
"""楼栋管理界面。"""
from services import building_service, house_service
from ui import menu
from ui.common_ui import pick_building, print_table
from utils import colors
from utils.inputs import CancelInput, ask_int, ask_str, confirm


def _form(default=None):
    d = default or {}
    return dict(
        code=ask_str('楼栋编号（如 1#）', required=True, default=d.get('code')),
        unit_count=ask_int('单元数', minv=1, maxv=20, default=d.get('unit_count') or 1),
        floors=ask_int('地上层数', minv=1, maxv=99, default=d.get('floors') or 1),
        has_elevator=confirm('是否有电梯？', default=bool(d.get('has_elevator'))),
        delivery_status=ask_str('交付状态（在建/未交付/已交付）', default=d.get('delivery_status') or '已交付',
                                max_len=10),
        remark=ask_str('备注', default=d.get('remark')),
    )


def add_ui(ctx):
    try:
        data = _form()
    except CancelInput:
        print('  已取消新增。')
        return
    bid = building_service.create(ctx.conn, ctx.community_id, data)
    print(colors.green(f'  [成功] 楼栋「{data["code"]}」已创建。'))


def edit_ui(ctx):
    b = pick_building(ctx, '请选择要修改的楼栋')
    if not b:
        return
    try:
        data = _form(default=dict(b))
    except CancelInput:
        print('  已取消修改。')
        return
    building_service.update(ctx.conn, b['id'], data)
    print(colors.green(f'  [成功] 楼栋「{data["code"]}」已更新。'))


def delete_ui(ctx):
    b = pick_building(ctx, '请选择要删除的楼栋')
    if not b:
        return
    n = building_service.house_count(ctx.conn, b['id'])
    print(colors.red(f'  !! 危险操作：将级联删除楼栋「{b["code"]}」及其下 {n} 套房屋、'
                     f'相关住户关系、账单与缴费数据，且不可恢复！'))
    if confirm(f'确认删除楼栋「{b["code"]}」？', default=False):
        building_service.delete(ctx.conn, b['id'])
        print(colors.green(f'  [成功] 楼栋「{b["code"]}」已删除。'))
    else:
        print('  已取消删除。')


def list_ui(ctx):
    rows = building_service.list_with_count(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 当前小区还没有楼栋。')
        return
    data = [[r['code'], r['unit_count'], r['floors'], '有' if r['has_elevator'] else '无',
             r['delivery_status'], r['house_count'], r['remark']]
            for r in rows]
    print_table(['楼栋编号', '单元数', '地上层数', '电梯', '交付状态', '房屋数', '备注'], data,
                ['l', 'r', 'r', 'l', 'l', 'r', 'l'])


def run(ctx):
    menu.run_menu(ctx, '楼栋管理', [
        ('1', '新增楼栋', add_ui),
        ('2', '修改楼栋', edit_ui),
        ('3', '删除楼栋', delete_ui),
        ('4', '楼栋列表', list_ui),
    ])
    return True
