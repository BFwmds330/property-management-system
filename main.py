# -*- coding: utf-8 -*-
"""智慧物业管理系统（终端版）—— 程序入口。

运行：python main.py
首次运行自动建库建表，并询问是否载入演示数据。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from context import AppContext
from models import APP_NAME, VERSION
from services import community_service, demo_data
from ui import (community_ui, extra_ui, fee_ui, house_ui, menu,
                report_ui, resident_ui, system_ui)
from utils import colors
from utils.inputs import CancelInput


def _setup_console():
    """Windows 控制台兼容：启用 ANSI 转义；输出编码异常时以替代符代替，避免崩溃。"""
    if os.name == 'nt':
        os.system('')
    try:
        sys.stdout.reconfigure(errors='replace')
        sys.stderr.reconfigure(errors='replace')
    except Exception:
        pass


def _welcome_setup(ctx):
    """首次运行引导：空库时询问是否载入演示数据。"""
    if community_service.count(ctx.conn) > 0:
        return
    print('  检测到首次运行，数据库已自动初始化（' + db.DB_PATH + '）。')
    try:
        ans = input('  是否载入演示数据？（y=载入 2 个小区的完整演示数据，n=空库开始）：').strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = 'n'
    if ans in ('y', 'yes', '是'):
        msg = demo_data.load_demo(ctx.conn)
        print(colors.green('  [成功] ' + msg))
    else:
        print('  已创建空库。请先进入"小区管理"新增小区并设为当前小区。')


def main():
    _setup_console()
    colors.enable()
    conn = db.connect()
    ctx = AppContext(conn)
    print('=' * 66)
    print(f'  欢迎使用 {APP_NAME} v{VERSION}（终端版，数据存储于本地 SQLite）')
    print('=' * 66)
    _welcome_setup(ctx)

    items = [
        ('1', '小区管理', community_ui.run),
        ('2', '房屋与户型管理', house_ui.run_root),
        ('3', '住户信息管理', resident_ui.run),
        ('4', '物业收费管理', fee_ui.run),
        ('5', '统计报表', report_ui.run),
        ('6', '公告与报修', extra_ui.run),
        ('7', '系统工具', system_ui.run),
    ]
    while True:
        menu.header(ctx)
        for k, label, _ in items:
            print(f'  {k}. {label}')
        print('  0. 退出系统')
        try:
            choice = input('请输入功能编号：').strip()
        except (EOFError, KeyboardInterrupt):
            print('\n再见，感谢使用！')
            return
        if choice == '0':
            print('再见，感谢使用！')
            return
        fn = next((f for k, _l, f in items if k == choice), None)
        if fn is None:
            print('  × 无效的功能编号，请重新输入。')
            continue
        try:
            fn(ctx)
        except CancelInput:
            print('  已取消当前操作。')
        except ValueError as e:
            print(colors.red(f'  × {e}'))
        except SystemExit:
            raise
        except Exception:
            menu.log_exception()
            print(colors.red('  × 操作出现异常，详情已记录到 data/error.log，请重试。'))


if __name__ == '__main__':
    main()
