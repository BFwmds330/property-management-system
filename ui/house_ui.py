# -*- coding: utf-8 -*-
"""房屋管理界面：登记、批量生成、筛选列表、详情、修改、状态变更、产权过户、删除。"""
from models import HOUSE_STATUSES
from services import extra_service, fee_service, house_service, resident_service
from ui import building_ui, housetype_ui, menu
from ui.common_ui import pick_building, pick_house, print_table
from utils import colors
from utils.dates import today_str
from utils.inputs import CancelInput, ask_date, ask_float, ask_int, ask_choice, ask_str, confirm
from utils import tables


# ---------- 房屋操作 ----------

def _area_form(default_gross=None, default_inner=None):
    gross = ask_float('建筑面积（㎡）', minv=0.01, default=default_gross)
    inner = ask_float('套内面积（㎡）', minv=0, default=default_inner or round(gross * 0.78, 2))
    return gross, inner


def add_ui(ctx):
    try:
        b = pick_building(ctx, '登记房屋 - 先选择楼栋')
        if not b:
            return
        if b['community_id'] != ctx.community_id:
            raise ValueError('所选楼栋不属于当前小区')
        unit = ask_int('单元号', minv=1, maxv=b['unit_count'], default=1)
        floor = ask_int('楼层', minv=1, maxv=99, default=1)
        room_no = ask_str('房号（如 1501）', required=True, default=f'{floor}01', max_len=10)
        gross, inner = _area_form()
        type_id = _pick_type_optional(ctx)
        status = ask_choice('房屋状态', [(s, s) for s in HOUSE_STATUSES], default='空置')
        remark = ask_str('备注')
    except CancelInput:
        print('  已取消登记。')
        return
    hid = house_service.create(ctx.conn, ctx.community_id, dict(
        building_id=b['id'], unit=unit, floor=floor, room_no=room_no,
        area_gross=gross, area_inner=inner, house_type_id=type_id,
        status=status, remark=remark))
    print(colors.green(f'  [成功] 房屋已登记：{b["code"]} {unit}单元 {room_no}室'))


def _pick_type_optional(ctx):
    """选择户型（0 = 不设置）。"""
    from services import housetype_service
    rows = housetype_service.list_with_count(ctx.conn, ctx.community_id)
    if not rows:
        print('  ! 户型库为空，房屋将不关联户型。')
        return None
    data = [[i + 1, r['name'], f'{r["rooms"]}室{r["halls"]}厅{r["baths"]}卫', f'{r["area"]:.2f}']
            for i, r in enumerate(rows)]
    print_table(['序号', '户型名称', '格局', '面积(㎡)'], data)
    idx = ask_int('请选择户型序号（0 = 不设置）', minv=0, maxv=len(rows), default=0)
    return rows[idx - 1]['id'] if idx else None


def batch_ui(ctx):
    try:
        b = pick_building(ctx, '批量生成 - 先选择楼栋')
        if not b:
            return
        unit_s = ask_str(f'单元号（1-{b["unit_count"]}，a=全部单元）', required=True, default='1', max_len=2)
        units = (list(range(1, b['unit_count'] + 1))
                 if unit_s.lower() == 'a' else [ask_int('单元号', minv=1, maxv=b['unit_count'])])
        if unit_s.lower() == 'a' and b['unit_count'] == 1:
            units = [1]
        floor_from = ask_int('起始楼层', minv=1, maxv=99, default=1)
        floor_to = ask_int('结束楼层', minv=floor_from, maxv=99, default=b['floors'])
        per_floor = ask_int('每层几户', minv=1, maxv=20, default=4)
        type_id = _pick_type_optional(ctx)
        area_choice = ask_choice('面积来源', [('1', '按户型建筑面积'), ('2', '统一输入建筑面积')],
                                 default='1' if type_id else '2')
        area_gross = area_inner = None
        if area_choice == '2':
            area_gross, area_inner = _area_form()
    except CancelInput:
        print('  已取消批量生成。')
        return
    total = len(units) * (floor_to - floor_from + 1) * per_floor
    if not confirm(f'将按规则生成 {total} 套房屋（楼栋 {b["code"]}、单元 {units}、'
                   f'{floor_from}-{floor_to} 层、每层 {per_floor} 户），确认？', default=True):
        print('  已取消。')
        return
    created = skipped = 0
    for u in units:
        c, s = house_service.batch_generate(ctx.conn, ctx.community_id, b, u, floor_from,
                                            floor_to, per_floor, type_id, area_gross, area_inner)
        created += c
        skipped += s
    print(colors.green(f'  [成功] 批量生成完成：新增 {created} 套，跳过已存在 {skipped} 套。'))


def list_ui(ctx):
    """多条件筛选 + 明细查看。"""
    rows = _filtered_rows(ctx)
    if rows is None:
        return
    if not rows:
        print('  ! 没有符合条件的房屋。')
        return
    data = [[i + 1, house_service.code_of(r), house_service.label_of(r),
             f'{r["area_gross"]:.2f}', r['tname'] or '-', r['status'],
             r['owner_name'] or '-', f'{r["arrears"] / 100:.2f}' if r['arrears'] else '-']
            for i, r in enumerate(rows)]
    print_table(['序号', '房号编码', '位置', '面积(㎡)', '户型', '状态', '业主', '欠费(元)'], data,
                ['l', 'l', 'l', 'r', 'l', 'l', 'l', 'r'])
    print(f'  共 {len(rows)} 套房屋')
    idx = ask_int('输入序号查看房屋详情（0 返回）', minv=0, maxv=len(rows), default=0)
    if idx:
        _detail(ctx, rows[idx - 1])


def _filtered_rows(ctx):
    kind = ask_choice('筛选方式',
                      [('1', '全部'), ('2', '按楼栋'), ('3', '按楼栋+单元'), ('4', '按房屋状态'),
                       ('5', '按户型'), ('6', '仅看欠费房屋'), ('7', '按关键字(房号/业主)')],
                      default='1')
    kw = building_id = unit = status = type_id = None
    only_arrears = False
    if kind == '2':
        b = pick_building(ctx)
        if not b:
            return None
        building_id = b['id']
    elif kind == '3':
        b = pick_building(ctx)
        if not b:
            return None
        building_id = b['id']
        unit = ask_int('单元号', minv=1, maxv=b['unit_count'], default=1)
    elif kind == '4':
        status = ask_choice('房屋状态', [(s, s) for s in HOUSE_STATUSES])
    elif kind == '5':
        type_id = _pick_type_optional(ctx)
        if not type_id:
            return None
    elif kind == '6':
        only_arrears = True
    elif kind == '7':
        kw = ask_str('输入房号/楼栋/业主姓名/手机号关键字', required=True)
    return house_service.search(ctx.conn, ctx.community_id, kw=kw or '', building_id=building_id,
                                unit=unit, status=status, house_type_id=type_id,
                                only_arrears=only_arrears, limit=200)


def _detail(ctx, h):
    """房屋详情：基本信息 + 在住住户 + 未缴账单。"""
    print(f'\n  ---- 房屋详情：{house_service.label_of(h)}（{house_service.code_of(h)}）----')
    print(f'  建筑面积：{h["area_gross"]:.2f}㎡   套内面积：{h["area_inner"]:.2f}㎡')
    print(f'  户型：{h["tname"] or "-"}   状态：{h["status"]}   入住日期：{h["checkin_date"] or "-"}')
    print(f'  业主：{h["owner_name"] or "-"}   备注：{h["remark"] or "-"}')
    residents = resident_service.list_of_house(ctx.conn, h['id'])
    if residents:
        data = [[r['rel_type'], r['relation'] or '-', r['name'], r['gender'],
                 r['phone'] or '-', r['id_number'] or '-',
                 ('常住' if r['is_living'] else '不常住'),
                 f'{r["rent_start"]}~{r["rent_end"]}' if r['rel_type'] == '租户' else
                 (r['start_date'] or '-')]
                for r in residents]
        print_table(['类型', '与业主关系', '姓名', '性别', '手机号', '证件号', '常住', '入住/租期'], data)
    else:
        print('  （当前无在住住户）')
    vehicles = extra_service.vehicles_of(ctx.conn, h['id'])
    if vehicles:
        print_table(['车牌号', '车位号', '备注'],
                    [[v['plate'], v['slot_no'] or '-', v['remark']] for v in vehicles])
    unpaid = fee_service.unpaid_bills(ctx.conn, h['id'])
    if unpaid:
        data = [[b['period'], b['item_name'] + (f'（车位 {b["unit_no"]}）' if b['unit_no'] else ''),
                 f'{b["amount_receivable"] / 100:.2f}',
                 f'{b["amount_received"] / 100:.2f}',
                 f'{(b["amount_receivable"] - b["amount_received"]) / 100:.2f}', b['status']]
                for b in unpaid]
        print_table(['账期', '收费项目', '应收(元)', '已收(元)', '余额(元)', '状态'], data,
                    ['l', 'l', 'r', 'r', 'r', 'l'])


def edit_ui(ctx):
    h = pick_house(ctx, '修改房屋信息 - 选择房屋')
    if not h:
        return
    try:
        unit = ask_int('单元号', minv=1, maxv=20, default=h['unit'])
        floor = ask_int('楼层', minv=1, maxv=99, default=h['floor'])
        room_no = ask_str('房号', required=True, default=h['room_no'], max_len=10)
        gross = ask_float('建筑面积（㎡）', minv=0.01, default=h['area_gross'])
        inner = ask_float('套内面积（㎡）', minv=0, default=h['area_inner'])
        type_id = _pick_type_optional(ctx)
        if type_id is None:
            type_id = h['house_type_id']
        remark = ask_str('备注', default=h['remark'])
    except CancelInput:
        print('  已取消修改。')
        return
    house_service.update(ctx.conn, h['id'], dict(
        unit=unit, floor=floor, room_no=room_no, area_gross=gross, area_inner=inner,
        house_type_id=type_id, remark=remark))
    print(colors.green(f'  [成功] 房屋「{house_service.label_of(h)}」信息已更新。'))


def status_ui(ctx):
    h = pick_house(ctx, '状态变更 - 选择房屋')
    if not h:
        return
    print(f'  当前状态：{h["status"]}')
    st = ask_choice('变更为', [(s, s) for s in HOUSE_STATUSES])
    house_service.set_status(ctx.conn, h['id'], st)
    print(colors.green(f'  [成功] 房屋「{house_service.label_of(h)}」状态变更为「{st}」。'))


def transfer_ui(ctx):
    """产权过户：留痕（旧业主转入历史记录）并写操作日志。"""
    h = pick_house(ctx, '产权过户 - 选择房屋')
    if not h:
        return
    if not h['owner_name']:
        print('  ! 该房屋当前无登记业主，将直接为新业主办理入住登记。')
    else:
        print(f'  当前业主：{h["owner_name"]}（过户后自动转入历史记录留痕）')
    src = ask_choice('新业主来源', [('1', '从已有住户档案中选择'), ('2', '新建业主档案')])
    new_rid = None
    try:
        if src == '1':
            kw = ask_str('输入姓名/手机号关键字', required=True)
            persons = resident_service.search_plain(ctx.conn, ctx.community_id, kw)
            if not persons:
                print('  ! 未找到匹配的住户档案。')
                return
            print_table(['序号', '姓名', '性别', '手机号', '证件号'],
                        [[i + 1, p['name'], p['gender'], p['phone'], p['id_number']]
                         for i, p in enumerate(persons)])
            idx = ask_int('选择新业主序号', minv=1, maxv=len(persons))
            new_rid = persons[idx - 1]['id']
            new_name = persons[idx - 1]['name']
        else:
            from ui.resident_ui import form_person
            person = form_person(required_phone=True)
            new_rid = resident_service.add_person(ctx.conn, person)
            new_name = person['name']
        date = ask_date('过户日期', default=today_str())
        if not confirm(f'确认将「{house_service.label_of(h)}」过户给 {new_name}？', default=False):
            print('  已取消过户。')
            return
    except CancelInput:
        print('  已取消过户。')
        return
    detail = house_service.transfer(ctx.conn, h['id'], new_rid, date)
    print(colors.green(f'  [成功] 产权过户完成：{detail}'))
    print('  （旧业主记录已转入该房屋的历史住户轨迹）')


def delete_ui(ctx):
    h = pick_house(ctx, '删除房屋 - 选择房屋')
    if not h:
        return
    n = house_service.bill_count(ctx.conn, h['id'])
    print(colors.red(f'  !! 危险操作：将级联删除房屋「{house_service.label_of(h)}」的住户关系'
                     f'与 {n} 笔账单及缴费流水，且不可恢复！'))
    if confirm('确认删除该房屋？', default=False):
        house_service.delete(ctx.conn, h['id'])
        print(colors.green(f'  [成功] 房屋「{house_service.label_of(h)}」已删除。'))
    else:
        print('  已取消删除。')


def run(ctx):
    menu.run_menu(ctx, '房屋管理', [
        ('1', '登记房屋', add_ui),
        ('2', '批量生成房屋', batch_ui),
        ('3', '房屋列表与筛选', list_ui),
        ('4', '修改房屋信息', edit_ui),
        ('5', '房屋状态变更', status_ui),
        ('6', '产权过户（留痕）', transfer_ui),
        ('7', '删除房屋', delete_ui),
    ])
    return True


def run_root(ctx):
    """二级菜单：楼栋 / 房屋 / 户型。"""
    menu.run_menu(ctx, '房屋与户型管理', [
        ('1', '楼栋管理', building_ui.run),
        ('2', '房屋管理', run),
        ('3', '户型管理', housetype_ui.run),
    ])
    return True
