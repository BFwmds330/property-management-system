# -*- coding: utf-8 -*-
"""菜单框架：统一的页头、多级菜单循环、异常兜底。"""
import os
import traceback
from datetime import datetime

from models import APP_NAME, VERSION
from utils import colors
from utils.inputs import CancelInput, pause

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERROR_LOG = os.path.join(_ROOT, 'data', 'error.log')


def header(ctx, title=''):
    print('=' * 66)
    name = ctx.community_name or '（未选择小区）'
    print(f'  {APP_NAME} v{VERSION}' + colors.cyan(f'        当前小区：{name}'))
    if title:
        print(f'  -- {title}')
    print('=' * 66)


def log_exception():
    """把未预期异常的堆栈记录到 data/error.log，保证程序不崩溃退出。"""
    try:
        os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f'\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{traceback.format_exc()}\n')
    except Exception:
        pass


def run_menu(ctx, title, items):
    """二级/三级菜单循环。items: [(编号, 名称, 处理函数), ...]；输入 0 返回上级。

    任何业务错误（ValueError）、主动取消（CancelInput）或未预期异常都只提示后继续，
    程序不会崩溃。
    """
    while True:
        header(ctx, title)
        for k, label, _ in items:
            print(f'  {k}. {label}')
        print('  0. 返回上级')
        try:
            choice = input('请输入功能编号：').strip()
        except (EOFError, KeyboardInterrupt):
            print('\n再见，感谢使用！')
            raise SystemExit(0)
        if choice == '0':
            return
        fn = next((f for k, _l, f in items if k == choice), None)
        if fn is None:
            print('  × 无效的功能编号，请重新输入。')
            continue
        try:
            result = fn(ctx)
        except CancelInput:
            print('  已取消当前操作。')
        except ValueError as e:
            print(colors.red(f'  × {e}'))
        except Exception:
            log_exception()
            print(colors.red('  × 操作出现异常，详情已记录到 data/error.log，请重试。'))
        else:
            # 子菜单运行器返回 True 表示"内部已自行交互完毕"，返回上级时不再重复暂停
            if result is not True:
                pause()


def ensure_community(ctx, switch_ui):
    """进入小区级菜单前的守卫：未选择小区时引导切换。返回是否可用。"""
    if ctx.community_id:
        return True
    print('  ! 尚未选择当前小区。')
    from utils.inputs import confirm
    if confirm('是否现在选择小区？', default=True):
        return switch_ui(ctx)
    return False
