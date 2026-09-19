# -*- coding: utf-8 -*-
"""物业收费业务（核心模块）：收费项目、账单生成、缴费登记、金额调整、欠费与催缴。

金额精度：账单/缴费金额一律以"分"（INTEGER）存储与运算，避免浮点误差。
账单状态流转：未缴 -> 部分缴纳 -> 已缴清（实收 >= 应收 即为已缴清）。
"""
from decimal import Decimal, ROUND_HALF_UP

from models import LATE_FEE_DAILY_RATE
from services import log_service
from services.house_service import label_of
from utils.dates import days_since, period_due


# ---------- 收费项目 ----------

def items(conn, cid, enabled_only=False):
    sql = 'SELECT * FROM fee_item WHERE community_id=?'
    if enabled_only:
        sql += ' AND enabled=1'
    return conn.execute(sql + ' ORDER BY id', (cid,)).fetchall()


def get_item(conn, iid):
    return conn.execute('SELECT * FROM fee_item WHERE id=?', (iid,)).fetchone()


def item_bill_count(conn, iid):
    return conn.execute('SELECT COUNT(*) FROM bill WHERE fee_item_id=?', (iid,)).fetchone()[0]


def create_item(conn, cid, d):
    name = (d.get('name') or '').strip()
    if not name:
        raise ValueError('收费项目名称不能为空')
    dup = conn.execute('SELECT 1 FROM fee_item WHERE community_id=? AND name=?', (cid, name)).fetchone()
    if dup:
        raise ValueError(f'收费项目「{name}」已存在')
    cur = conn.execute(
        'INSERT INTO fee_item(community_id,name,pricing_type,unit_price,fixed_amount,period_type,'
        'enabled,remark) VALUES (?,?,?,?,?,?,?,?)',
        (cid, name, d['pricing_type'], d.get('unit_price'), d.get('fixed_amount'),
         d.get('period_type') or '月', 1 if d.get('enabled', True) else 0, d.get('remark', '')))
    conn.commit()
    return cur.lastrowid


def update_item(conn, iid, d):
    row = get_item(conn, iid)
    if not row:
        raise ValueError('收费项目不存在')
    name = (d.get('name') or row['name']).strip()
    if not name:
        raise ValueError('收费项目名称不能为空')
    dup = conn.execute('SELECT id FROM fee_item WHERE community_id=? AND name=?',
                       (row['community_id'], name)).fetchone()
    if dup and dup['id'] != iid:
        raise ValueError(f'收费项目「{name}」已存在')
    conn.execute(
        'UPDATE fee_item SET name=?,pricing_type=?,unit_price=?,fixed_amount=?,period_type=?,'
        'enabled=?,remark=? WHERE id=?',
        (name, d.get('pricing_type', row['pricing_type']),
         d.get('unit_price', row['unit_price']), d.get('fixed_amount', row['fixed_amount']),
         d.get('period_type', row['period_type']),
         1 if d.get('enabled', row['enabled']) else 0,
         d.get('remark', row['remark']), iid))
    conn.commit()


def delete_item(conn, iid):
    row = get_item(conn, iid)
    if not row:
        raise ValueError('收费项目不存在')
    n = item_bill_count(conn, iid)
    if n:
        raise ValueError(f'该收费项目已有 {n} 笔账单引用，不能删除；如不再使用可将其"停用"')
    conn.execute('DELETE FROM fee_item WHERE id=?', (iid,))
    conn.commit()


def item_price_text(item):
    """计价标准的可读文本。"""
    if item['pricing_type'] == '面积单价':
        return f'{item["unit_price"]:.2f} 元/㎡/月'
    if item['pricing_type'] == '按户固定':
        return f'{item["fixed_amount"]:.2f} 元/户/{item["period_type"]}'
    return f'{item["fixed_amount"]:.2f} 元/车位/{item["period_type"]}（每车位单独出账）'


# ---------- 账单生成 ----------

def _months(period_type):
    return {'月': 1, '季': 3, '年': 12}.get(period_type, 1)


def _to_cents(yuan):
    """元（REAL）转分整数。"""
    return int((Decimal(str(yuan or 0)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def calc_amount(item, area_gross):
    """按计价标准计算单笔账单应收金额（分）；不适用（金额为 0）返回 None。

    按车位计费的账单按"每个车位一张账单"生成，见 preview_bills。
    """
    pt = item['pricing_type']
    if pt == '面积单价':
        if not area_gross:
            return None
        amt = Decimal(str(item['unit_price'] or 0)) * Decimal(str(area_gross)) * _months(item['period_type'])
    elif pt == '按户固定':
        amt = Decimal(str(item['fixed_amount'] or 0))
    else:  # 按车位：每个车位固定金额，由 preview_bills 逐车位调用
        amt = Decimal(str(item['fixed_amount'] or 0))
    cents = _to_cents(amt)
    return cents if cents > 0 else None


def bill_room_label(bill_row):
    """账单所属房号展示：车位分缴账单追加车位标识，如 1# 1单元 101室（车位 D001）。"""
    base = label_of(bill_row)
    unit = (bill_row['unit_no'] or '').strip() if 'unit_no' in bill_row.keys() else ''
    return f'{base}（车位 {unit}）' if unit else base


def _parking_slot_bills(conn, cid, item, period):
    """按车位计费的待生成明细：每个车位一条 {'house', 'cents', 'unit_no'}。"""
    rows = conn.execute(
        '''SELECT h.*, v.id AS vehicle_id, v.plate, v.slot_no, b.code AS bcode
           FROM house h
           JOIN building b ON b.id=h.building_id
           JOIN vehicle v ON v.house_id=h.id
           WHERE h.community_id=?
           ORDER BY b.id, h.unit, h.floor, h.room_no, v.id''', (cid,)).fetchall()
    cents = calc_amount(item, 0)
    if not cents:
        return [], 0
    used, entries, total = set(), [], 0
    for r in rows:
        unit = (r['slot_no'] or '').strip() or (r['plate'] or '').strip() or ''
        key = (r['id'], unit)
        n = 2
        while key in used:  # 车位号/车牌重复时追加序号，保证同户同账期唯一
            unit = f'{unit}-{n}'
            key = (r['id'], unit)
            n += 1
        used.add(key)
        entries.append({'house': r, 'cents': cents, 'unit_no': unit})
        total += cents
    return entries, total


def check_legacy_parking_bills(conn, item, period):
    """旧版本位费为"整户一张账单"（unit_no=''）。该账期存在旧账单时阻止重新生成，避免重复计费。"""
    if item['pricing_type'] != '按车位':
        return
    n = conn.execute(
        "SELECT COUNT(*) FROM bill WHERE fee_item_id=? AND period=? AND unit_no=''",
        (item['id'], period)).fetchone()[0]
    if n:
        raise ValueError(
            f'该账期已存在旧版整户车位费账单 {n} 笔。为避免重复计费，'
            f'请先在"账单查询"中删除其中未缴的账单后再生成，或改用其他账期。')


def preview_bills(conn, cid, item, period):
    """预览账单生成结果：返回 (entries, 应收合计分)。

    entries 元素：{'house': 房屋行, 'cents': 应收分, 'unit_no': 分缴单元标识}
    按车位计费时每个车位一条；其余计价方式每个房屋一条（unit_no=''）。
    """
    check_legacy_parking_bills(conn, item, period)
    if item['pricing_type'] == '按车位':
        return _parking_slot_bills(conn, cid, item, period)
    houses = conn.execute(
        '''SELECT h.*, b.code AS bcode FROM house h JOIN building b ON b.id=h.building_id
           WHERE h.community_id=? ORDER BY b.id, h.unit, h.floor, h.room_no''', (cid,)).fetchall()
    entries, total = [], 0
    for h in houses:
        cents = calc_amount(item, h['area_gross'])
        if cents:
            entries.append({'house': h, 'cents': cents, 'unit_no': ''})
            total += cents
    return entries, total


def generate(conn, cid, item, period):
    """为范围内全部适用对象生成账单（已存在的房-项目-账期-分缴单元自动跳过）。"""
    entries, total = preview_bills(conn, cid, item, period)
    created = skipped = 0
    for e in entries:
        h = e['house']
        dup = conn.execute(
            'SELECT 1 FROM bill WHERE house_id=? AND fee_item_id=? AND period=? AND unit_no=?',
            (h['id'], item['id'], period, e['unit_no'])).fetchone()
        if dup:
            skipped += 1
            continue
        conn.execute(
            "INSERT INTO bill(community_id,house_id,fee_item_id,period,original_amount,"
            "amount_receivable,status,unit_no) VALUES (?,?,?,?,?,?,'未缴',?)",
            (cid, h['id'], item['id'], period, e['cents'], e['cents'], e['unit_no']))
        created += 1
    conn.commit()
    return created, skipped, total


def delete_bill(conn, bill_id):
    """删除账单（仅限未缴且无任何缴费记录），写入操作日志。"""
    b = get_bill(conn, bill_id)
    if not b:
        raise ValueError('账单不存在或已被删除')
    if b['amount_received'] > 0:
        raise ValueError('该账单已有缴费记录，不能删除；如需调整请使用"账单金额调整"')
    conn.execute('DELETE FROM bill WHERE id=?', (bill_id,))
    conn.commit()
    log_service.add(conn, b['community_id'], '删除账单',
                    f'{bill_room_label(b)} {b["period"]} {b["item_name"]} '
                    f'应收 {b["amount_receivable"] / 100:.2f} 元')


# ---------- 账单查询 ----------

_BILL_SELECT = '''
SELECT b.*, i.name AS item_name, i.period_type AS item_period_type,
       h.room_no, h.unit, bld.code AS bcode, r.name AS owner_name
FROM bill b
JOIN fee_item i ON i.id=b.fee_item_id
JOIN house h ON h.id=b.house_id
JOIN building bld ON bld.id=h.building_id
LEFT JOIN resident r ON r.id=h.owner_resident_id
'''


def get_bill(conn, bid):
    return conn.execute(_BILL_SELECT + ' WHERE b.id=?', (bid,)).fetchone()


def bills_query(conn, cid, *, kw='', item_id=None, period='', status='', limit=500):
    sql = _BILL_SELECT + ' WHERE b.community_id=?'
    args = [cid]
    if kw:
        like = f'%{kw}%'
        sql += ' AND (h.room_no LIKE ? OR bld.code LIKE ? OR r.name LIKE ?)'
        args += [like] * 3
    if item_id:
        sql += ' AND b.fee_item_id=?'
        args.append(item_id)
    if period:
        sql += ' AND b.period=?'
        args.append(period)
    if status:
        sql += ' AND b.status=?'
        args.append(status)
    sql += ' ORDER BY b.period DESC, bld.id, h.unit, h.room_no LIMIT ?'
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def bills_of_house(conn, house_id):
    return conn.execute(
        _BILL_SELECT + ' WHERE b.house_id=? ORDER BY b.period, b.id', (house_id,)).fetchall()


def unpaid_bills(conn, house_id):
    return conn.execute(
        _BILL_SELECT + ' WHERE b.house_id=? AND b.amount_receivable>b.amount_received '
        'ORDER BY b.period, b.id', (house_id,)).fetchall()


# ---------- 缴费与调整 ----------

def _status(receivable, received):
    if received >= receivable:
        return '已缴清'
    if received > 0:
        return '部分缴纳'
    return '未缴'


def pay(conn, bill_id, amount, pay_date, method, receipt_no, operator, remark=''):
    """登记一笔缴费（支持部分缴费），自动更新账单余额与状态。"""
    b = conn.execute('SELECT * FROM bill WHERE id=?', (bill_id,)).fetchone()
    if not b:
        raise ValueError('账单不存在或已被删除')
    balance = b['amount_receivable'] - b['amount_received']
    if balance <= 0:
        raise ValueError('该账单已缴清，无需再缴费')
    if amount <= 0:
        raise ValueError('缴费金额必须大于 0')
    if amount > balance:
        raise ValueError(f'缴费金额超过欠缴余额 {balance / 100:.2f} 元')
    conn.execute(
        'INSERT INTO payment(bill_id,community_id,amount,pay_date,method,receipt_no,operator,remark) '
        'VALUES (?,?,?,?,?,?,?,?)',
        (bill_id, b['community_id'], amount, pay_date, method, receipt_no, operator, remark))
    received = b['amount_received'] + amount
    st = _status(b['amount_receivable'], received)
    conn.execute('UPDATE bill SET amount_received=?, status=? WHERE id=?', (received, st, bill_id))
    conn.commit()
    return st


def adjust(conn, bill_id, new_receivable, reason, operator='前台'):
    """手动调整账单应收金额（减免/优惠），必须填写原因并写入操作日志留痕。"""
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('减免/调整必须填写原因（留痕要求）')
    b = conn.execute('SELECT * FROM bill WHERE id=?', (bill_id,)).fetchone()
    if not b:
        raise ValueError('账单不存在或已被删除')
    if new_receivable < 0:
        raise ValueError('调整后金额不能为负数')
    conn.execute(
        'UPDATE bill SET amount_receivable=?, adjust_amount=?, adjust_reason=?, status=? WHERE id=?',
        (new_receivable, new_receivable - b['original_amount'], reason,
         _status(new_receivable, b['amount_received']), bill_id))
    conn.commit()
    detail = (f'账单#{bill_id}（{b["period"]}）应收 '
              f'{b["amount_receivable"] / 100:.2f} -> {new_receivable / 100:.2f} 元，原因：{reason}')
    log_service.add(conn, b['community_id'], '账单调整', detail, operator)
    return detail


# ---------- 欠费与催缴 ----------

def arrears_rows(conn, cid):
    """欠费清单：附欠费天数（按计费周期期末起算）与预估滞纳金（日万分之五）。"""
    rows = conn.execute(
        '''SELECT b.*, i.name AS item_name, h.room_no, h.unit, bld.code AS bcode,
                  r.name AS owner_name, r.phone AS owner_phone
           FROM bill b
           JOIN fee_item i ON i.id=b.fee_item_id
           JOIN house h ON h.id=b.house_id
           JOIN building bld ON bld.id=h.building_id
           LEFT JOIN resident r ON r.id=h.owner_resident_id
           WHERE b.community_id=? AND b.amount_receivable>b.amount_received
           ORDER BY b.period, bld.id, h.unit, h.room_no''', (cid,)).fetchall()
    out = []
    for b in rows:
        item = get_item(conn, b['fee_item_id'])
        balance = b['amount_receivable'] - b['amount_received']
        due = period_due(item['period_type'] if item else '月', b['period'])
        days = days_since(due)
        late_fee = int(balance * LATE_FEE_DAILY_RATE * days)
        out.append({
            'bill': b, 'balance': balance, 'due': due, 'days': days, 'late_fee': late_fee,
        })
    # 欠费天数多的排前面
    out.sort(key=lambda x: x['days'], reverse=True)
    return out


def sms_text(community_name, house_label, item_name, period, owner_name,
             balance_cents, days, service_phone):
    """生成一段催缴短信文本。"""
    return (f'【智慧物业】尊敬的{owner_name or "业主"}：您在{community_name}{house_label}的'
            f'{item_name}（账期{period}）已欠费{balance_cents / 100:.2f}元，'
            f'欠费{days}天。为不影响您正常享受物业服务，请尽快至物业服务中心缴纳，'
            f'支持现金/银行转账/扫码。咨询电话：{service_phone or "物业前台"}。')


# ---------- 缴费记录 ----------

def payments_query(conn, cid, *, kw='', item_id=None, date_from='', date_to='', limit=1000):
    sql = '''
SELECT p.*, b.period, b.unit_no, i.name AS item_name, h.room_no, h.unit, bld.code AS bcode, r.name AS owner_name
FROM payment p
JOIN bill b ON b.id=p.bill_id
JOIN fee_item i ON i.id=b.fee_item_id
JOIN house h ON h.id=b.house_id
JOIN building bld ON bld.id=h.building_id
LEFT JOIN resident r ON r.id=h.owner_resident_id
WHERE p.community_id=?'''
    args = [cid]
    if kw:
        like = f'%{kw}%'
        sql += ' AND (h.room_no LIKE ? OR bld.code LIKE ? OR r.name LIKE ?)'
        args += [like] * 3
    if item_id:
        sql += ' AND b.fee_item_id=?'
        args.append(item_id)
    if date_from:
        sql += ' AND p.pay_date>=?'
        args.append(date_from)
    if date_to:
        sql += ' AND p.pay_date<=?'
        args.append(date_to)
    sql += ' ORDER BY p.pay_date DESC, p.id DESC LIMIT ?'
    args.append(limit)
    return conn.execute(sql, args).fetchall()
