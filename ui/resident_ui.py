# -*- coding: utf-8 -*-
"""住户信息管理界面：业主入住、家庭成员、租户、搬出退租、历史轨迹、搜索、通讯录、车辆。"""
from models import GENDERS, ID_TYPES, LEASE_REMIND_DAYS, MEMBER_RELATIONS
from services import extra_service, house_service, resident_service
from ui import menu
from ui.common_ui import pick_house, print_table
from utils import colors, tables
from utils import exporter
from utils.dates import days_until, today_str
from utils.inputs import (CancelInput, ask_choice, ask_date, ask_money,
                          ask_str, confirm)
from utils.validators import check_general_id, check_id_card, check_phone, id_card_birth


def form_person(required_phone=True):
    """人员信息表单（业主/家庭成员/租户共用），返回字段字典。"""
    name = ask_str('姓名', required=True, max_len=30)
    gender = ask_choice('性别', [(g, g) for g in GENDERS], default='保密')
    birth = ask_date('出生日期')
    id_type = ask_choice('证件类型', [(t, t) for t in ID_TYPES], default='身份证')
    while True:
        id_number = ask_str(f'{id_type}证件号', required=True, max_len=30)
        if id_type == '身份证':
            ok, v = check_id_card(id_number)
        else:
            ok, v = check_general_id(id_number)
        if ok:
            id_number = v
            break
        print(f'  × {v}')
    if not birth and id_type == '身份证':
        birth = id_card_birth(id_number)
    phone = ''
    while True:
        s = ask_str('手机号' + ('' if required_phone else '（可留空）'),
                    required=required_phone, max_len=11)
        if not s:
            break
        ok, v = check_phone(s)
        if ok:
            phone = v
            break
        print(f'  × {v}')
    return dict(
        name=name, gender=gender, birth_date=birth, id_type=id_type, id_number=id_number,
        phone=phone,
        wechat=ask_str('微信号', max_len=30),
        workplace=ask_str('工作单位', max_len=50),
        emergency_contact=ask_str('紧急联系人姓名', max_len=30),
        emergency_phone=ask_str('紧急联系人电话', max_len=20),
        remark=ask_str('备注'),
    )


def owner_register_ui(ctx):
    try:
        h = pick_house(ctx, '业主入住登记 - 选择房屋')
        if not h:
            return
        exist = resident_service.current_link(ctx.conn, h['id'], '业主')
        if exist:
            raise ValueError(f'该房屋已有业主（{exist["rname"]}），如需更换请使用"产权过户"功能')
        print('  —— 请录入业主信息 ——')
        person = form_person(required_phone=True)
        checkin = ask_date('入住日期', default=today_str())
        if not confirm(f'确认登记 {person["name"]} 为「{house_service.label_of(h)}」业主？', default=True):
            print('  已取消登记。')
            return
    except CancelInput:
        print('  已取消登记。')
        return
    rid = resident_service.add_person(ctx.conn, person)
    resident_service.link(ctx.conn, h['id'], rid, '业主', start_date=checkin)
    print(colors.green(f'  [成功] 业主 {person["name"]} 已登记入住「{house_service.label_of(h)}」。'))


def member_add_ui(ctx):
    try:
        h = pick_house(ctx, '添加家庭成员 - 选择房屋')
        if not h:
            return
        print('  —— 请录入家庭成员信息 ——')
        person = form_person(required_phone=False)
        relation = ask_choice('与业主关系', [(r, r) for r in MEMBER_RELATIONS])
        living = confirm('是否常住？', default=True)
    except CancelInput:
        print('  已取消。')
        return
    rid = resident_service.add_person(ctx.conn, person)
    resident_service.link(ctx.conn, h['id'], rid, '家庭成员', relation=relation,
                          start_date=today_str(), is_living=1 if living else 0)
    print(colors.green(f'  [成功] 家庭成员 {person["name"]}（{relation}）已登记至「{house_service.label_of(h)}」。'))


def tenant_add_ui(ctx):
    try:
        h = pick_house(ctx, '登记租户 - 选择房屋')
        if not h:
            return
        if h['status'] != '出租':
            if confirm('该房屋状态不是"出租"，是否同时将房屋状态改为"出租"？', default=True):
                pass
            else:
                print('  已取消登记。')
                return
        print('  —— 请录入租户信息 ——')
        person = form_person(required_phone=True)
        rent_start = ask_date('租期开始日期', default=today_str())
        rent_end = ask_date('租期结束日期', required=True)
        rent_monthly = None
        if confirm('是否登记月租金？', default=False):
            rent_monthly = ask_money('月租金（元）', required=False, allow_zero=False)
            if rent_monthly is not None:
                rent_monthly = rent_monthly / 100.0
        if not confirm(f'确认登记 {person["name"]} 为「{house_service.label_of(h)}」租户？', default=True):
            print('  已取消登记。')
            return
    except CancelInput:
        print('  已取消登记。')
        return
    rid = resident_service.add_person(ctx.conn, person)
    resident_service.link(ctx.conn, h['id'], rid, '租户', start_date=rent_start,
                          rent_start=rent_start, rent_end=rent_end, rent_monthly=rent_monthly)
    if h['status'] != '出租':
        house_service.set_status(ctx.conn, h['id'], '出租')
    left = days_until(rent_end)
    print(colors.green(f'  [成功] 租户 {person["name"]} 已登记至「{house_service.label_of(h)}」。'))
    if left is not None and left <= LEASE_REMIND_DAYS:
        print(colors.yellow(f'  ! 提醒：该租约将于 {rent_end} 到期（剩余 {max(left, 0)} 天）。'))


def house_residents_ui(ctx):
    h = pick_house(ctx, '房屋住户列表 - 选择房屋')
    if not h:
        return
    residents = resident_service.list_of_house(ctx.conn, h['id'])
    if not residents:
        print('  ! 该房屋暂无在住住户。')
        return
    data = [[r['rel_type'], r['relation'] or '-', r['name'], r['gender'],
             r['phone'] or '-', r['id_number'] or '-',
             '常住' if r['is_living'] else '不常住', r['emergency_contact'] or '-',
             f'{r["rent_start"]}~{r["rent_end"]}' if r['rel_type'] == '租户' else
             (r['start_date'] or '-')]
            for r in residents]
    print(f'  房屋：{house_service.label_of(h)}（业主：{h["owner_name"] or "-"}）')
    print_table(['类型', '与业主关系', '姓名', '性别', '手机号', '证件号', '常住', '紧急联系人', '入住/租期'],
                data)


def person_edit_ui(ctx):
    kw = ask_str('输入姓名/手机号搜索要修改的住户', required=True)
    persons = resident_service.search_plain(ctx.conn, ctx.community_id, kw, limit=15)
    if not persons:
        print('  ! 未找到匹配的住户档案。')
        return
    print_table(['序号', '姓名', '性别', '手机号', '证件号', '工作单位'],
                [[i + 1, p['name'], p['gender'], p['phone'], p['id_number'], p['workplace']]
                 for i, p in enumerate(persons)])
    idx = ask_int('选择要修改的住户序号（0 取消）', minv=0, maxv=len(persons), default=0)
    if not idx:
        return
    p = persons[idx - 1]
    try:
        data = dict(
            name=ask_str('姓名', required=True, default=p['name'], max_len=30),
            gender=ask_choice('性别', [(g, g) for g in GENDERS], default=p['gender']),
            birth_date=ask_date('出生日期', default=p['birth_date'] or None),
            phone=ask_str('手机号', default=p['phone'], max_len=11),
            wechat=ask_str('微信号', default=p['wechat'], max_len=30),
            workplace=ask_str('工作单位', default=p['workplace'], max_len=50),
            emergency_contact=ask_str('紧急联系人姓名', default=p['emergency_contact'], max_len=30),
            emergency_phone=ask_str('紧急联系人电话', default=p['emergency_phone'], max_len=20),
            remark=ask_str('备注', default=p['remark']),
        )
    except CancelInput:
        print('  已取消修改。')
        return
    if data['phone'] and data['phone'] != p['phone']:
        ok, v = check_phone(data['phone'])
        if not ok:
            raise ValueError(v)
        data['phone'] = v
    resident_service.update_person(ctx.conn, p['id'], data)
    print(colors.green(f'  [成功] 住户「{data["name"]}」资料已更新。'))


def move_out_ui(ctx):
    h = pick_house(ctx, '住户搬出/退租 - 选择房屋')
    if not h:
        return
    residents = resident_service.list_of_house(ctx.conn, h['id'])
    if not residents:
        print('  ! 该房屋暂无在住住户。')
        return
    data = [[i + 1, r['rel_type'], r['relation'] or '-', r['name'], r['phone'] or '-']
            for i, r in enumerate(residents)]
    print_table(['序号', '类型', '与业主关系', '姓名', '手机号'], data)
    idx = ask_int('选择要办理搬出/退租的住户序号（0 取消）', minv=0, maxv=len(residents), default=0)
    if not idx:
        return
    r = residents[idx - 1]
    end = ask_date(f'{r["name"]} 的搬出日期', default=today_str())
    if not confirm(f'确认 {r["name"]}（{r["rel_type"]}）自 {end} 起搬出？', default=False):
        print('  已取消。')
        return
    row = resident_service.move_out(ctx.conn, r['id'], end)
    print(colors.green(f'  [成功] {row["rname"]}（{row["rel_type"]}）已办理搬出，记录转入历史轨迹。'))
    if row['rel_type'] == '租户':
        if confirm('是否将房屋状态改为"空置"？', default=False):
            house_service.set_status(ctx.conn, h['id'], '空置')
    elif row['rel_type'] == '业主':
        print('  （房屋产权人已清空，状态置为"空置"；如需更换业主请使用"产权过户"）')


def history_ui(ctx):
    h = pick_house(ctx, '历史住户轨迹 - 选择房屋')
    if not h:
        return
    rows = resident_service.history_of_house(ctx.conn, h['id'])
    if not rows:
        print('  ! 该房屋暂无住户记录。')
        return
    data = [[r['rel_type'], r['relation'] or '-', r['name'], r['phone'] or '-',
             r['start_date'] or '-', r['end_date'] or '-',
             '在住' if r['is_current'] else '历史']
            for r in rows]
    print(f'  房屋：{house_service.label_of(h)} 历史住户轨迹')
    print_table(['类型', '与业主关系', '姓名', '手机号', '入住/起', '搬出/止', '状态'], data)


def search_ui(ctx):
    kw = ask_str('输入姓名/手机号/房号关键字', required=True)
    rows = resident_service.search_residents(ctx.conn, ctx.community_id, kw)
    if not rows:
        print('  ! 未找到匹配的在住住户。')
        return
    data = [[r['name'], r['rel_type'], r['relation'] or '-',
             f'{r["bcode"]} {r["unit"]}单元 {r["room_no"]}室', r['phone'] or '-', r['id_number'] or '-']
            for r in rows]
    print_table(['姓名', '类型', '与业主关系', '房屋', '手机号', '证件号'], data)
    print(f'  共 {len(rows)} 条记录')


def directory_export_ui(ctx):
    rows = resident_service.directory_rows(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 当前小区暂无在住住户，无内容可导出。')
        return
    headers = ['房号', '人员类型', '与业主关系', '姓名', '性别', '手机号', '证件号', '微信号',
               '工作单位', '紧急联系人', '紧急联系电话', '是否常住', '入住日期', '租期止', '月租金(元)', '备注']
    path = exporter.export_csv(f'住户通讯录_{ctx.community_name}', headers, rows)
    print(colors.green(f'  [成功] 已导出 {len(rows)} 条住户通讯录 -> {path}'))


def lease_remind_ui(ctx):
    rows = resident_service.lease_expiring(ctx.conn, ctx.community_id, LEASE_REMIND_DAYS)
    if not rows:
        print(f'  ! 当前小区没有 {LEASE_REMIND_DAYS} 天内到期的租约。')
        return
    data = []
    for r in rows:
        left = days_until(r['rent_end'])
        tag = colors.red(f'已过期{-left}天') if left < 0 else f'剩余 {left} 天'
        data.append([f'{r["bcode"]} {r["unit"]}单元 {r["room_no"]}室', r['name'],
                     r['phone'] or '-', r['rent_start'], r['rent_end'], tag])
    print_table(['房屋', '租户', '手机号', '租期开始', '租期结束', '到期情况'], data)
    print(f'  共 {len(rows)} 份租约 {LEASE_REMIND_DAYS} 天内到期（或已过期未退租），请及时跟进。')


def vehicle_ui(ctx):
    h = pick_house(ctx, '车辆信息 - 选择房屋')
    if not h:
        return
    while True:
        rows = extra_service.vehicles_of(ctx.conn, h['id'])
        print(f'\n  房屋：{house_service.label_of(h)} 车辆信息')
        if rows:
            print_table(['编号', '车牌号', '车位号', '备注'],
                        [[v['id'], v['plate'], v['slot_no'] or '-', v['remark']] for v in rows])
        else:
            print('  （未登记车辆）')
        act = ask_choice('操作', [('1', '添加车辆'), ('2', '删除车辆'), ('0', '返回')])
        if act == '0':
            return
        if act == '1':
            plate = ask_str('车牌号（如 京A12345）', required=True, max_len=8)
            slot = ask_str('车位号（可留空）', max_len=20)
            remark = ask_str('备注')
            extra_service.add_vehicle(ctx.conn, h['id'], plate, slot, remark)
            print(colors.green('  [成功] 车辆已登记。'))
        else:
            if not rows:
                continue
            vid = ask_int('输入要删除的车辆编号（0 取消）', minv=0)
            if vid:
                extra_service.delete_vehicle(ctx.conn, vid)
                print(colors.green('  [成功] 车辆已删除。'))


def run(ctx):
    menu.run_menu(ctx, '住户信息管理', [
        ('1', '业主入住登记', owner_register_ui),
        ('2', '添加家庭成员', member_add_ui),
        ('3', '登记租户', tenant_add_ui),
        ('4', '房屋住户列表', house_residents_ui),
        ('5', '修改住户资料', person_edit_ui),
        ('6', '住户搬出/退租', move_out_ui),
        ('7', '房屋住户历史轨迹', history_ui),
        ('8', '住户搜索（姓名/手机号/房号）', search_ui),
        ('9', '导出住户通讯录 CSV', directory_export_ui),
        ('10', '租约到期提醒', lease_remind_ui),
        ('11', '车辆信息登记', vehicle_ui),
    ])
    return True
