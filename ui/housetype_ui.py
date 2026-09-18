# -*- coding: utf-8 -*-
"""户型管理界面。"""
from services import housetype_service
from ui import menu
from ui.common_ui import print_table
from utils import colors
from utils.inputs import CancelInput, ask_float, ask_int, ask_choice, ask_str, confirm

ORIENTATIONS = ['南', '南北通透', '东南', '东', '西', '北']


def _form(default=None):
    d = default or {}
    return dict(
        name=ask_str('户型名称（如：三室两厅两卫 A 户型）', required=True, default=d.get('name')),
        rooms=ask_int('室（卧室数量）', minv=0, maxv=9, default=d.get('rooms') or 2),
        halls=ask_int('厅（客厅数量）', minv=0, maxv=9, default=d.get('halls') or 1),
        baths=ask_int('卫（卫生间数量）', minv=0, maxv=9, default=d.get('baths') or 1),
        area=ask_float('建筑面积（㎡，作为批量生成默认值）', minv=0, default=d.get('area') or None),
        orientation=ask_choice('朝向', [(o, o) for o in ORIENTATIONS], default=d.get('orientation') or '南'),
        has_balcony=confirm('是否带阳台？', default=bool(d.get('has_balcony'))),
        has_bay_window=confirm('是否带飘窗？', default=bool(d.get('has_bay_window'))),
        has_garden=confirm('是否带入户花园？', default=bool(d.get('has_garden'))),
        remark=ask_str('备注', default=d.get('remark')),
    )


def add_ui(ctx):
    try:
        data = _form()
    except CancelInput:
        print('  已取消新增。')
        return
    tid = housetype_service.create(ctx.conn, ctx.community_id, data)
    print(colors.green(f'  [成功] 户型「{data["name"]}」已加入户型库。'))


def edit_ui(ctx):
    rows = housetype_service.list_with_count(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 户型库为空，请先新增。')
        return
    _list_table(rows)
    tid = ask_int('请输入要修改的户型编号（0 取消）', minv=0)
    if not tid:
        return
    row = housetype_service.get(ctx.conn, tid)
    if not row or row['community_id'] != ctx.community_id:
        raise ValueError('户型编号不存在')
    n = housetype_service.used_count(ctx.conn, tid)
    if n:
        print(colors.yellow(f'  ! 注意：该户型正被 {n} 套房屋引用，修改后这些房屋的户型信息将同步变化。'))
        if not confirm('确认继续修改？', default=True):
            print('  已取消修改。')
            return
    try:
        data = _form(default=dict(row))
    except CancelInput:
        print('  已取消修改。')
        return
    housetype_service.update(ctx.conn, tid, data)
    print(colors.green(f'  [成功] 户型「{data["name"]}」已更新。'))


def delete_ui(ctx):
    rows = housetype_service.list_with_count(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 户型库为空。')
        return
    _list_table(rows)
    tid = ask_int('请输入要删除的户型编号（0 取消）', minv=0)
    if not tid:
        return
    row = housetype_service.get(ctx.conn, tid)
    if not row or row['community_id'] != ctx.community_id:
        raise ValueError('户型编号不存在')
    if confirm(f'确认删除户型「{row["name"]}」？', default=False):
        housetype_service.delete(ctx.conn, tid)
        print(colors.green('  [成功] 户型已删除。'))
    else:
        print('  已取消删除。')


def _list_table(rows):
    data = [[r['id'], r['name'], f'{r["rooms"]}室{r["halls"]}厅{r["baths"]}卫',
             f'{r["area"]:.2f}', r['orientation'],
             ('带' if r['has_balcony'] else '') + ('飘窗' if r['has_bay_window'] else '')
             + ('花园' if r['has_garden'] else '') or '-',
             r['house_count']] for r in rows]
    print_table(['编号', '户型名称', '格局', '面积(㎡)', '朝向', '配置', '引用房屋数'], data,
                ['l', 'l', 'l', 'r', 'l', 'l', 'r'])


def list_ui(ctx):
    rows = housetype_service.list_with_count(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 户型库为空。')
        return
    _list_table(rows)


def distribution_ui(ctx):
    rows = housetype_service.distribution(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 暂无数据。')
        return
    total = sum(r['cnt'] for r in rows)
    data = [[r['name'], r['cnt'], f'{r["cnt"] / total * 100:.1f}%'] for r in rows]
    print_table(['户型名称', '房屋数量', '占比'], data, ['l', 'r', 'r'])
    print(f'  合计：{total} 套房屋')


def run(ctx):
    menu.run_menu(ctx, '户型管理', [
        ('1', '新增户型', add_ui),
        ('2', '修改户型', edit_ui),
        ('3', '删除户型', delete_ui),
        ('4', '户型列表', list_ui),
        ('5', '户型分布统计', distribution_ui),
    ])
    return True
