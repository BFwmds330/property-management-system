# -*- coding: utf-8 -*-
"""物业收费管理界面：收费项目配置、生成账单、缴费登记、欠费管理、催缴与记录查询。"""
from models import PAY_METHODS
from services import fee_service, house_service, log_service
from ui import menu
from ui.common_ui import pick_fee_item, pick_house, print_table
from utils import colors, tables
from utils import exporter
from utils.dates import today_str
from utils.inputs import (CancelInput, ask_date, ask_int, ask_choice, ask_money,
                          ask_period, ask_str, confirm)
from utils.validators import check_int


# ---------- 收费项目配置 ----------

def _item_form(default=None):
    d = default or {}
    name = ask_str('项目名称（如 物业费）', required=True, default=d.get('name'))
    pricing = ask_choice('计价方式',
                         [('1', '面积单价（元/㎡/月）'), ('2', '按户固定金额'),
                          ('3', '按车位数量')], default=d.get('pricing_type_key') or '1')
    period_type = ask_choice('计费周期', [('月', '月'), ('季', '季'), ('年', '年')],
                             default=d.get('period_type') or '月')
    unit_price = fixed = None
    if pricing == '1':
        unit_price = ask_money('单价（元/㎡/月）', required=True, allow_zero=False,
                               default=d.get('unit_price')) / 100.0
    elif pricing == '2':
        fixed = ask_money(f'每户金额（元/{period_type}）', required=True, allow_zero=False,
                          default=d.get('fixed_amount')) / 100.0
    else:
        fixed = ask_money(f'每车位金额（元/位/{period_type}）', required=True, allow_zero=False,
                          default=d.get('fixed_amount')) / 100.0
    enabled = confirm('是否启用？', default=bool(d.get('enabled', True)))
    remark = ask_str('备注', default=d.get('remark'))
    return dict(name=name, pricing_type=fee_service_key(pricing), unit_price=unit_price,
                fixed_amount=fixed, period_type=period_type, enabled=enabled, remark=remark)


def fee_service_key(k):
    return {'1': '面积单价', '2': '按户固定', '3': '按车位'}[k]


def item_add_ui(ctx):
    try:
        data = _item_form()
    except CancelInput:
        print('  已取消新增。')
        return
    fee_service.create_item(ctx.conn, ctx.community_id, data)
    print(colors.green(f'  [成功] 收费项目「{data["name"]}」已创建。'))


def item_edit_ui(ctx):
    item = pick_fee_item(ctx, '请选择要修改的收费项目')
    if not item:
        return
    try:
        data = _item_form(default=dict(item, pricing_type_key={'面积单价': '1', '按户固定': '2', '按车位': '3'}[item['pricing_type']]))
    except CancelInput:
        print('  已取消修改。')
        return
    fee_service.update_item(ctx.conn, item['id'], data)
    print(colors.green(f'  [成功] 收费项目「{data["name"]}」已更新。'))


def item_delete_ui(ctx):
    item = pick_fee_item(ctx, '请选择要删除的收费项目')
    if not item:
        return
    if confirm(f'确认删除收费项目「{item["name"]}」？（有账单引用时将被拒绝）', default=False):
        fee_service.delete_item(ctx.conn, item['id'])
        print(colors.green('  [成功] 收费项目已删除。'))
    else:
        print('  已取消删除。')


def item_list_ui(ctx):
    rows = fee_service.items(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 暂无收费项目。')
        return
    data = [[r['id'], r['name'], r['pricing_type'], fee_service.item_price_text(r),
             r['period_type'], '启用' if r['enabled'] else '停用', r['remark']]
            for r in rows]
    print_table(['编号', '项目名称', '计价方式', '计价标准', '计费周期', '状态', '备注'], data)


def item_config_run(ctx):
    menu.run_menu(ctx, '收费项目配置', [
        ('1', '新增收费项目', item_add_ui),
        ('2', '修改收费项目', item_edit_ui),
        ('3', '删除收费项目', item_delete_ui),
        ('4', '收费项目列表', item_list_ui),
    ])
    return True


# ---------- 生成账单 ----------

def generate_ui(ctx):
    try:
        item = pick_fee_item(ctx, '生成账单 - 选择收费项目', enabled_only=True)
        if not item:
            return
        period = ask_period(f'输入账期（{item["period_type"]}账）', item['period_type'])
    except CancelInput:
        print('  已取消。')
        return
    entries, total = fee_service.preview_bills(ctx.conn, ctx.community_id, item, period)
    if not entries:
        print('  ! 没有适用的收费对象'
              + ('（按车位计费需房屋名下已登记车辆，每个车位单独出账）。' if item['pricing_type'] == '按车位' else '。'))
        return
    preview = []
    for e in entries[:8]:
        h = e['house']
        preview.append([fee_service.bill_room_label(
            {'bcode': h['bcode'], 'unit': h['unit'], 'room_no': h['room_no'],
             'unit_no': e['unit_no']}), f'{e["cents"] / 100:.2f}'])
    print_table(['房号', '应收金额(元)'], preview)
    if len(entries) > 8:
        print(f'  ……（仅预览前 8 条，共 {len(entries)} 笔）')
    tip = '（车位费按车位分缴：每个车位一张账单，可独立缴费）' if item['pricing_type'] == '按车位' else ''
    print(f'  预计生成 {len(entries)} 笔账单，应收总额 {tables.money(total)} 元'
          f'（已存在的账单将自动跳过）。{tip}')
    if not confirm('确认生成？', default=True):
        print('  已取消生成。')
        return
    created, skipped, _ = fee_service.generate(ctx.conn, ctx.community_id, item, period)
    print(colors.green(f'  [成功] 账单生成完成：新生成 {created} 笔，跳过已存在 {skipped} 笔。'))


def _bill_rows(bills):
    return [[b['period'], fee_service.bill_room_label(b), b['owner_name'] or '-', b['item_name'],
             f'{b["amount_receivable"] / 100:.2f}', f'{b["amount_received"] / 100:.2f}',
             f'{(b["amount_receivable"] - b["amount_received"]) / 100:.2f}', b['status'],
             f'{b["adjust_amount"] / 100:+.2f}' if b['adjust_amount'] else '-']
            for b in bills]


def bill_query_ui(ctx):
    try:
        kw = ask_str('房号/业主关键字（可留空）')
        item = None
        if confirm('是否按收费项目筛选？', default=False):
            item = pick_fee_item(ctx)
        period = ask_str('账期（如 2026-09，可留空）', max_len=10)
        status = ask_choice('账单状态', [('0', '全部'), ('1', '未缴'), ('2', '部分缴纳'), ('3', '已缴清')],
                            default='0')
    except CancelInput:
        print('  已取消。')
        return
    bills = fee_service.bills_query(ctx.conn, ctx.community_id, kw=kw,
                                    item_id=item['id'] if item else None,
                                    period=period,
                                    status={'0': '', '1': '未缴', '2': '部分缴纳',
                                            '3': '已缴清'}[status])
    if not bills:
        print('  ! 没有符合条件的账单。')
        return
    print_table(['账期', '房号', '业主', '收费项目', '应收(元)', '已收(元)', '余额(元)', '状态', '调整'],
                _bill_rows(bills), ['l', 'l', 'l', 'l', 'r', 'r', 'r', 'l', 'r'])
    recv = sum(b['amount_receivable'] for b in bills)
    paid = sum(b['amount_received'] for b in bills)
    print(f'  共 {len(bills)} 笔：应收 {tables.money(recv)} 元，已收 {tables.money(paid)} 元，'
          f'余额 {tables.money(recv - paid)} 元')
    if confirm('是否导出本结果为 CSV？', default=False):
        path = exporter.export_csv(
            f'账单查询_{ctx.community_name}',
            ['账期', '房号', '业主', '收费项目', '应收(元)', '已收(元)', '余额(元)', '状态', '调整(元)'],
            [[c for c in row] for row in _bill_rows(bills)])
        print(colors.green(f'  [成功] 已导出 -> {path}'))
    idx = ask_int('输入序号可删除对应"未缴"账单（仅限无任何缴费记录，0 跳过）',
                  minv=0, maxv=len(bills), default=0)
    if idx:
        b = bills[idx - 1]
        if confirm(f'确认删除账单：{fee_service.bill_room_label(b)} {b["period"]} '
                   f'{b["item_name"]}（应收 {b["amount_receivable"] / 100:.2f} 元）？', default=False):
            fee_service.delete_bill(ctx.conn, b['id'])
            print(colors.green('  [成功] 账单已删除并写入操作日志。'))
        else:
            print('  已取消删除。')


# ---------- 缴费登记 ----------

def _ask_pay_common(default_bill_id=0):
    pay_date = ask_date('缴费日期', default=today_str())
    method = ask_choice('支付方式', [(m, m) for m in PAY_METHODS], default='扫码')
    receipt = ask_str('收据号（可留空）', max_len=30,
                      default=f'{today_str().replace("-", "")}{default_bill_id}')
    operator = ask_str('经办人', default='前台', max_len=20)
    return pay_date, method, receipt, operator


def pay_register_ui(ctx):
    try:
        h = pick_house(ctx, '登记缴费 - 选择房屋')
        if not h:
            return
        bills = fee_service.unpaid_bills(ctx.conn, h['id'])
        if not bills:
            print(colors.green('  该房屋没有未缴清账单。'))
            return
        print(f'  房屋：{house_service.label_of(h)}（业主：{h["owner_name"] or "-"}）未缴清账单：')
        print_table(['序号', '账期', '收费项目', '应收(元)', '已收(元)', '余额(元)'],
                    [[i + 1, b['period'], b['item_name'], f'{b["amount_receivable"] / 100:.2f}',
                      f'{b["amount_received"] / 100:.2f}',
                      f'{(b["amount_receivable"] - b["amount_received"]) / 100:.2f}']
                     for i, b in enumerate(bills)], ['l', 'l', 'l', 'r', 'r', 'r'])
        mode = ask_str('输入要缴费的账单序号（部分缴费请输入金额前先选账单）；a=一次缴清全部',
                       required=True, max_len=3)
        if mode.lower() == 'a':
            total = sum(b['amount_receivable'] - b['amount_received'] for b in bills)
            if not confirm(f'将一次缴清 {len(bills)} 笔账单，合计 {tables.money(total)} 元，确认？',
                           default=True):
                print('  已取消。')
                return
            pay_date, method, receipt, operator = _ask_pay_common()
            for b in bills:
                balance = b['amount_receivable'] - b['amount_received']
                fee_service.pay(ctx.conn, b['id'], balance, pay_date, method, receipt, operator)
                print(f'    · {b["period"]} {b["item_name"]}：缴清 {tables.money(balance)} 元')
            print(colors.green('  [成功] 全部账单已缴清。'))
            return
        ok, idx = check_int(mode, 1, len(bills))
        if not ok:
            raise ValueError(idx)
        b = bills[idx - 1]
        balance = b['amount_receivable'] - b['amount_received']
        amount = ask_money(f'本次实缴金额（元，欠缴余额 {balance / 100:.2f}，支持部分缴费）',
                           required=True, allow_zero=False, default=balance / 100)
        pay_date, method, receipt, operator = _ask_pay_common(b['id'])
        if not confirm(f'确认缴费：{b["period"]} {b["item_name"]}，金额 {amount / 100:.2f} 元？',
                       default=True):
            print('  已取消。')
            return
        st = fee_service.pay(ctx.conn, b['id'], amount, pay_date, method, receipt, operator)
        if st == '已缴清':
            print(colors.green('  [成功] 缴费登记完成，该账单已缴清。'))
        else:
            print(colors.yellow(f'  [成功] 缴费登记完成，账单状态：{st}（仍有余额）。'))
    except CancelInput:
        print('  已取消缴费。')


def adjust_ui(ctx):
    """账单金额调整（减免/优惠），必须填原因并写操作日志。"""
    try:
        h = pick_house(ctx, '账单调整 - 选择房屋')
        if not h:
            return
        bills = fee_service.bills_of_house(ctx.conn, h['id'])
        if not bills:
            print('  ! 该房屋暂无账单。')
            return
        print_table(['序号', '账期', '收费项目', '应收(元)', '已收(元)', '余额(元)', '状态'],
                    [[i + 1, b['period'], b['item_name'], f'{b["amount_receivable"] / 100:.2f}',
                      f'{b["amount_received"] / 100:.2f}',
                      f'{(b["amount_receivable"] - b["amount_received"]) / 100:.2f}', b['status']]
                     for i, b in enumerate(bills)], ['l', 'l', 'l', 'r', 'r', 'r', 'l'])
        idx = ask_int('选择要调整的账单序号（0 取消）', minv=0, maxv=len(bills), default=0)
        if not idx:
            return
        b = bills[idx - 1]
        print(f'  当前应收 {b["amount_receivable"] / 100:.2f} 元（生成时 '
              f'{b["original_amount"] / 100:.2f} 元，累计已调整 {b["adjust_amount"] / 100:+.2f} 元）')
        new_amount = ask_money('调整后应收金额（元）', required=True, allow_zero=True,
                               default=b['amount_receivable'] / 100)
        reason = ask_str('调整原因（必填，将留痕）', required=True, max_len=100)
        if not confirm(f'确认将 {b["period"]} {b["item_name"]} 应收金额调整为 '
                       f'{new_amount / 100:.2f} 元？', default=False):
            print('  已取消。')
            return
    except CancelInput:
        print('  已取消。')
        return
    detail = fee_service.adjust(ctx.conn, b['id'], new_amount, reason)
    print(colors.green(f'  [成功] 账单调整完成并已写入操作日志：{detail}'))


# ---------- 欠费管理 ----------

def _arrears_data(rows):
    data = []
    for a in rows:
        b = a['bill']
        tag = '超90天' if a['days'] > 90 else ''
        data.append([fee_service.bill_room_label(b), b['owner_name'] or '-', b['item_name'],
                     b['period'], f'{a["balance"] / 100:.2f}', a['days'],
                     f'{a["late_fee"] / 100:.2f}', tag])
    return data


def arrears_ui(ctx):
    rows = fee_service.arrears_rows(ctx.conn, ctx.community_id)
    if not rows:
        print(colors.green('  当前小区没有欠费账单。'))
        return
    data = []
    for a in rows:
        row = _arrears_data([a])[0]
        if a['days'] > 90:
            row = [colors.red(str(c)) for c in row]
        data.append(row)
    print_table(['房号', '业主', '收费项目', '账期', '欠费金额(元)', '欠费天数', '预估滞纳金(元)', '标记'],
                data, ['l', 'l', 'l', 'l', 'r', 'r', 'r', 'l'])
    total = sum(a['balance'] for a in rows)
    print(f'  共 {len(rows)} 笔欠费，合计 {tables.money(total)} 元'
          f'（滞纳金按日万分之五估算，仅供参考）')


def demand_export_ui(ctx):
    rows = fee_service.arrears_rows(ctx.conn, ctx.community_id)
    if not rows:
        print('  当前小区没有欠费账单，无需导出。')
        return
    headers = ['房号', '业主', '联系电话', '收费项目', '账期', '欠费金额(元)', '欠费天数',
               '预估滞纳金(元)', '催缴说明']
    data = []
    for a in rows:
        b = a['bill']
        data.append([fee_service.bill_room_label(b), b['owner_name'] or '-', b['owner_phone'] or '',
                     b['item_name'], b['period'], f'{a["balance"] / 100:.2f}', a['days'],
                     f'{a["late_fee"] / 100:.2f}',
                     f'请于见单后 7 日内缴清欠费，欠费超 90 天将按约定处理。'])
    path = exporter.export_csv(f'催缴单_{ctx.community_name}', headers, data)
    print(colors.green(f'  [成功] 已导出 {len(rows)} 条催缴单 -> {path}'))


def sms_ui(ctx):
    rows = fee_service.arrears_rows(ctx.conn, ctx.community_id)
    if not rows:
        print('  当前小区没有欠费账单。')
        return
    data = [[i + 1, fee_service.bill_room_label(a['bill']), a['bill']['owner_name'] or '-',
             a['bill']['item_name'], a['bill']['period'], f'{a["balance"] / 100:.2f}', a['days']]
            for i, a in enumerate(rows)]
    print_table(['序号', '房号', '业主', '收费项目', '账期', '欠费金额(元)', '欠费天数'], data,
                ['l', 'l', 'l', 'l', 'l', 'r', 'r'])
    idx = ask_int('选择要生成催缴短信的欠费序号（0 取消）', minv=0, maxv=len(rows), default=0)
    if not idx:
        return
    a = rows[idx - 1]
    from services import community_service
    comm = community_service.get(ctx.conn, ctx.community_id)
    text = fee_service.sms_text(comm['name'], fee_service.bill_room_label(a['bill']),
                                a['bill']['item_name'], a['bill']['period'],
                                a['bill']['owner_name'], a['balance'], a['days'],
                                comm['service_phone'])
    print('\n  -------- 催缴短信预览 --------')
    print('  ' + text)
    print('  -------------------------------')
    if confirm('是否保存为文本文件？', default=False):
        path = exporter.export_text(f'催缴短信_{a["bill"]["owner_name"] or a["bill"]["room_no"]}', text)
        print(colors.green(f'  [成功] 已保存 -> {path}'))


def payment_query_ui(ctx):
    try:
        kw = ask_str('房号/业主关键字（可留空）')
        item = None
        if confirm('是否按收费项目筛选？', default=False):
            item = pick_fee_item(ctx)
        date_from = ask_date('缴费日期起（如 2026-09-01，可留空）')
        date_to = ask_date('缴费日期止（可留空）')
    except CancelInput:
        print('  已取消。')
        return
    rows = fee_service.payments_query(ctx.conn, ctx.community_id, kw=kw,
                                      item_id=item['id'] if item else None,
                                      date_from=date_from, date_to=date_to)
    if not rows:
        print('  ! 没有符合条件的缴费记录。')
        return
    data = [[p['pay_date'], fee_service.bill_room_label(p), p['owner_name'] or '-', p['item_name'],
             p['period'], f'{p["amount"] / 100:.2f}', p['method'], p['receipt_no'],
             p['operator']] for p in rows]
    print_table(['缴费日期', '房号', '业主', '收费项目', '账期', '金额(元)', '方式', '收据号', '经办人'],
                data, ['l', 'l', 'l', 'l', 'l', 'r', 'l', 'l', 'l'])
    total = sum(p['amount'] for p in rows)
    print(f'  共 {len(rows)} 笔缴费流水，合计 {tables.money(total)} 元')
    if confirm('是否导出为 CSV？', default=False):
        path = exporter.export_csv(
            f'缴费记录_{ctx.community_name}',
            ['缴费日期', '房号', '业主', '收费项目', '账期', '金额(元)', '方式', '收据号', '经办人'],
            data)
        print(colors.green(f'  [成功] 已导出 -> {path}'))


def run(ctx):
    menu.run_menu(ctx, '物业收费管理', [
        ('1', '收费项目配置', item_config_run),
        ('2', '生成账单', generate_ui),
        ('3', '账单查询', bill_query_ui),
        ('4', '登记缴费（支持部分缴费）', pay_register_ui),
        ('5', '欠费清单', arrears_ui),
        ('6', '导出催缴单 CSV', demand_export_ui),
        ('7', '模拟催缴短信', sms_ui),
        ('8', '缴费记录查询', payment_query_ui),
        ('9', '账单金额调整（减免留痕）', adjust_ui),
    ])
    return True
