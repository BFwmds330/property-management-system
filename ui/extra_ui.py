# -*- coding: utf-8 -*-
"""扩展功能界面：小区公告管理与报修登记。"""
from models import REPAIR_STATUSES
from services import extra_service
from ui import menu
from ui.common_ui import pick_house, print_table
from utils import colors
from utils.dates import today_str
from utils.inputs import CancelInput, ask_date, ask_choice, ask_int, ask_str, confirm


def _ann_list(ctx):
    return extra_service.announcements(ctx.conn, ctx.community_id)


def ann_add_ui(ctx):
    try:
        title = ask_str('公告标题', required=True, max_len=60)
        content = ask_str('公告内容', required=True, max_len=500)
        date = ask_date('发布日期', default=today_str())
    except CancelInput:
        print('  已取消。')
        return
    extra_service.add_announcement(ctx.conn, ctx.community_id, title, content, date)
    print(colors.green(f'  [成功] 公告「{title}」已发布。'))


def ann_list_ui(ctx):
    rows = _ann_list(ctx)
    if not rows:
        print('  ! 暂无公告。')
        return
    print_table(['编号', '标题', '发布日期'],
                [[r['id'], r['title'], r['publish_date']] for r in rows])
    aid = ask_int('输入编号查看公告全文（0 返回）', minv=0, default=0)
    if aid:
        row = extra_service.get_announcement(ctx.conn, aid)
        if not row or row['community_id'] != ctx.community_id:
            print('  ! 公告编号不存在。')
            return
        print('\n  ' + '-' * 50)
        print(f'  【{row["title"]}】（{row["publish_date"]}）')
        print(f'  {row["content"]}')
        print('  ' + '-' * 50)


def ann_edit_ui(ctx):
    rows = _ann_list(ctx)
    if not rows:
        print('  ! 暂无公告。')
        return
    print_table(['编号', '标题', '发布日期'],
                [[r['id'], r['title'], r['publish_date']] for r in rows])
    aid = ask_int('输入要修改的公告编号（0 取消）', minv=0, default=0)
    if not aid:
        return
    row = extra_service.get_announcement(ctx.conn, aid)
    if not row or row['community_id'] != ctx.community_id:
        raise ValueError('公告编号不存在')
    try:
        title = ask_str('公告标题', required=True, default=row['title'], max_len=60)
        content = ask_str('公告内容', required=True, default=row['content'], max_len=500)
        date = ask_date('发布日期', default=row['publish_date'] or None)
    except CancelInput:
        print('  已取消。')
        return
    extra_service.update_announcement(ctx.conn, aid, title, content, date)
    print(colors.green('  [成功] 公告已更新。'))


def ann_delete_ui(ctx):
    rows = _ann_list(ctx)
    if not rows:
        print('  ! 暂无公告。')
        return
    print_table(['编号', '标题', '发布日期'],
                [[r['id'], r['title'], r['publish_date']] for r in rows])
    aid = ask_int('输入要删除的公告编号（0 取消）', minv=0, default=0)
    if not aid:
        return
    if confirm('确认删除该公告？', default=False):
        extra_service.delete_announcement(ctx.conn, aid)
        print(colors.green('  [成功] 公告已删除。'))
    else:
        print('  已取消删除。')


def repair_add_ui(ctx):
    try:
        print('  选择报修房屋（输入 0 跳过 = 公共区域报修）')
        h = pick_house(ctx, '报修登记 - 选择房屋')
        content = ask_str('报修内容', required=True, max_len=200)
    except CancelInput:
        print('  已取消。')
        return
    extra_service.add_repair(ctx.conn, ctx.community_id, h['id'] if h else None, content)
    print(colors.green('  [成功] 报修已登记，状态：待处理。'))


def _repair_table(rows):
    data = []
    for r in rows:
        room = f'{r["bcode"]} {r["unit"]}单元 {r["room_no"]}室' if r['house_id'] else '（公共区域）'
        data.append([r['id'], room, (r['content'][:18] + '...') if len(r['content']) > 20
                     else r['content'], r['status'], r['handler'] or '-', r['created_at'][:10],
                     r['finished_at'] or '-'])
    print_table(['编号', '房屋', '报修内容', '状态', '处理人', '登记日期', '完成日期'], data,
                ['l', 'l', 'l', 'l', 'l', 'l', 'l'])


def repair_list_ui(ctx):
    st = ask_choice('按状态筛选', [('0', '全部')] + [(s, s) for s in REPAIR_STATUSES], default='0')
    rows = extra_service.repairs(ctx.conn, ctx.community_id,
                                 status='' if st == '0' else st)
    if not rows:
        print('  ! 暂无报修记录。')
        return
    _repair_table(rows)


def repair_flow_ui(ctx):
    rows = extra_service.repairs(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 暂无报修记录。')
        return
    _repair_table(rows)
    rid = ask_int('输入要处理的报修编号（0 取消）', minv=0, default=0)
    if not rid:
        return
    row = extra_service.get_repair(ctx.conn, rid)
    if not row or row['community_id'] != ctx.community_id:
        raise ValueError('报修编号不存在')
    print(f'  当前状态：{row["status"]}（待处理 -> 处理中 -> 已完成）')
    st = ask_choice('流转到', [(s, s) for s in REPAIR_STATUSES], default='处理中')
    handler = ask_str('处理人（可留空）', default=row['handler'], max_len=20)
    result = ask_str('处理结果备注（状态为"已完成"时建议填写）', max_len=200)
    extra_service.update_repair(ctx.conn, rid, st, handler, result)
    print(colors.green(f'  [成功] 报修 #{rid} 状态已更新为「{st}」。'))


def announcement_run(ctx):
    menu.run_menu(ctx, '小区公告管理', [
        ('1', '发布公告', ann_add_ui),
        ('2', '公告列表/查看', ann_list_ui),
        ('3', '修改公告', ann_edit_ui),
        ('4', '删除公告', ann_delete_ui),
    ])
    return True


def repair_run(ctx):
    menu.run_menu(ctx, '报修管理', [
        ('1', '报修登记', repair_add_ui),
        ('2', '报修列表', repair_list_ui),
        ('3', '状态流转/处理', repair_flow_ui),
    ])
    return True


def run(ctx):
    menu.run_menu(ctx, '公告与报修', [
        ('1', '小区公告管理', announcement_run),
        ('2', '报修管理', repair_run),
    ])
    return True
