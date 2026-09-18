# -*- coding: utf-8 -*-
"""系统工具：数据备份/恢复、操作日志、演示数据重置、关于。"""
import os

import db
from services import community_service, demo_data, log_service
from ui import menu
from ui.common_ui import print_table
from utils import colors
from utils.inputs import ask_int, confirm


def backup_ui(ctx):
    path = db.backup_db()
    log_service.add(ctx.conn, ctx.community_id, '数据备份', f'备份到 {path}')
    print(colors.green(f'  [成功] 数据已备份 -> {path}'))
    print('  提示：也可直接复制 data/property.db 文件进行冷备份。')


def restore_ui(ctx):
    backups = db.list_backups()
    if not backups:
        print('  ! 暂无备份文件，请先执行"备份数据库"。')
        return
    print_table(['序号', '备份文件', '大小', '备份时间'],
                [[i + 1, fn, f'{size / 1024:.1f} KB', ts] for i, (fn, size, ts) in enumerate(backups)])
    idx = ask_int('选择要恢复的备份序号（0 取消）', minv=0, default=0)
    if not idx:
        return
    fn = backups[idx - 1][0]
    path = os.path.join(db.DATA_DIR, 'backups', fn)
    print(colors.red('  !! 恢复将覆盖当前全部数据，且不可撤销！'))
    if confirm(f'确认用备份「{fn}」覆盖当前数据库？', default=False):
        ctx.conn.close()
        db.restore_db(path)
        ctx.conn = db.connect()
        ctx.community_id = None
        ctx.community_name = None
        log_service.add(ctx.conn, None, '数据恢复', f'已从 {fn} 恢复')
        print(colors.green('  [成功] 数据恢复完成，请重新选择当前小区。'))
    else:
        print('  已取消恢复。')


def logs_ui(ctx):
    rows = log_service.recent(ctx.conn, 50, ctx.community_id)
    if not rows:
        print('  ! 暂无操作日志。')
        return
    comm_names = {c['id']: c['name'] for c in community_service.all(ctx.conn)}
    data = [[r['id'], r['created_at'],
             comm_names.get(r['community_id'], '（全局）') if r['community_id'] else '（全局）',
             r['action'], (r['detail'][:40] + '...') if len(r['detail']) > 42 else r['detail'],
             r['operator']] for r in rows]
    print_table(['编号', '时间', '小区', '操作', '详情', '经办人'], data)
    print(f'  （最近 {len(rows)} 条；关键操作含删除小区、产权过户、账单调整、备份恢复等）')


def demo_reset_ui(ctx):
    print(colors.red('  !! 重置将【清空当前数据库全部业务数据】并重新载入演示数据，不可恢复！'))
    print('  建议先执行"备份数据库"。')
    if not confirm('确认清空并重新载入演示数据？', default=False):
        print('  已取消。')
        return
    if not confirm('再次确认：真的要清空全部数据吗？', default=False):
        print('  已取消。')
        return
    msg = demo_data.load_demo(ctx.conn, reset=True)
    ctx.community_id = None
    ctx.community_name = None
    print(colors.green(f'  [成功] {msg}'))


def about_ui(ctx):
    from models import APP_NAME, VERSION
    print(f'  {APP_NAME} v{VERSION}')
    print('  - 面向物业管理公司的终端（命令行）信息化管理系统')
    print('  - 技术栈：Python 3.10+ 标准库 + SQLite，零第三方依赖，单机可用')
    print(f'  - 数据文件：{db.DB_PATH}')
    print('  - 使用帮助：见项目 README.md；数据模型与菜单结构：见 docs/DESIGN.md')
    print('  - 数据备份：data/backups/；导出文件：data/exports/')


def run(ctx):
    menu.run_menu(ctx, '系统工具', [
        ('1', '备份数据库', backup_ui),
        ('2', '恢复数据库', restore_ui),
        ('3', '查看操作日志', logs_ui),
        ('4', '重置并重载演示数据', demo_reset_ui),
        ('5', '关于本系统', about_ui),
    ])
    return True
