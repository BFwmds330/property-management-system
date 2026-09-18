# -*- coding: utf-8 -*-
"""房屋业务：登记、批量生成、多条件筛选、状态变更、产权过户（留痕）、删除。"""
from services import log_service

# 房屋联查视图：附楼栋编号、户型名、业主姓名与当前欠费
_SELECT = '''
SELECT h.*, b.code AS bcode, t.name AS tname, r.name AS owner_name,
  (SELECT IFNULL(SUM(amount_receivable-amount_received),0) FROM bill
    WHERE house_id=h.id AND amount_receivable>amount_received) AS arrears
FROM house h
JOIN building b ON b.id=h.building_id
LEFT JOIN house_type t ON t.id=h.house_type_id
LEFT JOIN resident r ON r.id=h.owner_resident_id
'''


def get_full(conn, hid):
    return conn.execute(_SELECT + ' WHERE h.id=?', (hid,)).fetchone()


def code_of(row):
    """房号唯一编码，如 3-2-15-1501（楼栋-单元-楼层-房号）。"""
    bcode = (row['bcode'] or '').rstrip('#')
    return f'{bcode}-{row["unit"]}-{row["floor"]}-{row["room_no"]}'


def label_of(row):
    """位置描述，如 1# 2单元 1501室。"""
    return f'{row["bcode"]} {row["unit"]}单元 {row["room_no"]}室'


def search(conn, cid, kw='', building_id=None, unit=None, status=None,
           house_type_id=None, only_arrears=False, limit=100):
    """多条件筛选房屋列表（kw 匹配房号/楼栋/业主姓名/业主手机号）。"""
    sql = _SELECT + ' WHERE h.community_id=?'
    args = [cid]
    if building_id:
        sql += ' AND h.building_id=?'
        args.append(building_id)
    if unit:
        sql += ' AND h.unit=?'
        args.append(unit)
    if status:
        sql += ' AND h.status=?'
        args.append(status)
    if house_type_id:
        sql += ' AND h.house_type_id=?'
        args.append(house_type_id)
    if only_arrears:
        sql += " AND h.id IN (SELECT house_id FROM bill WHERE amount_receivable>amount_received)"
    if kw:
        like = f'%{kw}%'
        sql += ' AND (h.room_no LIKE ? OR b.code LIKE ? OR r.name LIKE ? OR r.phone LIKE ?)'
        args += [like, like, like, like]
    sql += ' ORDER BY b.id, h.unit, h.floor, h.room_no LIMIT ?'
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def count_all(conn, cid):
    return conn.execute('SELECT COUNT(*) FROM house WHERE community_id=?', (cid,)).fetchone()[0]


def exists(conn, building_id, unit, floor, room_no):
    return conn.execute(
        'SELECT 1 FROM house WHERE building_id=? AND unit=? AND floor=? AND room_no=?',
        (building_id, unit, floor, room_no)).fetchone()


def create(conn, cid, data):
    from services import building_service
    building = building_service.get(conn, data['building_id'])
    if not building or building['community_id'] != cid:
        raise ValueError('所选楼栋不存在或不属于当前小区')
    room_no = (data.get('room_no') or '').strip()
    if not room_no:
        raise ValueError('房号不能为空（如 1501）')
    unit = int(data.get('unit') or 1)
    floor = int(data.get('floor') or 1)
    if exists(conn, building['id'], unit, floor, room_no):
        raise ValueError(f'房屋已存在：{building["code"]} {unit}单元 {room_no}室，请勿重复登记')
    cur = conn.execute(
        'INSERT INTO house(community_id,building_id,unit,floor,room_no,area_gross,area_inner,'
        'house_type_id,status,remark) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (cid, building['id'], unit, floor, room_no,
         data.get('area_gross') or 0, data.get('area_inner') or 0,
         data.get('house_type_id'), data.get('status') or '空置', data.get('remark', '')))
    conn.commit()
    return cur.lastrowid


def batch_generate(conn, cid, building, unit, floor_from, floor_to, per_floor,
                   house_type_id=None, area_gross=None, area_inner=None):
    """按规则批量生成房屋，返回 (生成数量, 跳过数量)。

    房号规则：楼层号 + 两位序号，如 15 层 3 号 -> 1503。
    area_gross 为空时取户型建筑面积；套内面积缺省按建筑面积的 78% 估算。
    """
    type_area = None
    if house_type_id:
        t = conn.execute('SELECT * FROM house_type WHERE id=? AND community_id=?',
                         (house_type_id, cid)).fetchone()
        if not t:
            raise ValueError('所选户型不存在或不属于当前小区')
        type_area = t['area']
    created = skipped = 0
    for f in range(floor_from, floor_to + 1):
        for i in range(1, per_floor + 1):
            room_no = f'{f}{i:02d}'
            if exists(conn, building['id'], unit, f, room_no):
                skipped += 1
                continue
            g = area_gross if area_gross else (type_area or 0)
            inner = area_inner if area_inner else round(g * 0.78, 2)
            conn.execute(
                'INSERT INTO house(community_id,building_id,unit,floor,room_no,area_gross,'
                'area_inner,house_type_id,status) VALUES (?,?,?,?,?,?,?,?, "空置")',
                (cid, building['id'], unit, f, room_no, g, inner, house_type_id))
            created += 1
    conn.commit()
    return created, skipped


def update(conn, hid, data):
    h = get_full(conn, hid)
    if not h:
        raise ValueError('房屋不存在或已被删除')
    room_no = (data.get('room_no') or h['room_no']).strip()
    if not room_no:
        raise ValueError('房号不能为空')
    dup = exists(conn, h['building_id'], data.get('unit', h['unit']),
                 data.get('floor', h['floor']), room_no)
    if dup:
        row = conn.execute('SELECT id FROM house WHERE building_id=? AND unit=? AND floor=? AND room_no=?',
                           (h['building_id'], data.get('unit', h['unit']),
                            data.get('floor', h['floor']), room_no)).fetchone()
        if row and row['id'] != hid:
            raise ValueError(f'修改后的房号与现有房屋重复：{h["bcode"]} '
                             f'{data.get("unit", h["unit"])}单元 {room_no}室')
    conn.execute(
        'UPDATE house SET unit=?,floor=?,room_no=?,area_gross=?,area_inner=?,house_type_id=?,remark=? '
        'WHERE id=?',
        (data.get('unit', h['unit']), data.get('floor', h['floor']), room_no,
         data.get('area_gross', h['area_gross']), data.get('area_inner', h['area_inner']),
         data.get('house_type_id', h['house_type_id']), data.get('remark', h['remark']), hid))
    conn.commit()


def set_status(conn, hid, status):
    conn.execute('UPDATE house SET status=? WHERE id=?', (status, hid))
    conn.commit()


def transfer(conn, hid, new_resident_id, date_str):
    """产权过户：旧业主关系记录转历史（保留 end_date），新业主登记入住，并写入操作日志。"""
    h = get_full(conn, hid)
    if not h:
        raise ValueError('房屋不存在或已被删除')
    new_resident = conn.execute('SELECT * FROM resident WHERE id=?', (new_resident_id,)).fetchone()
    if not new_resident:
        raise ValueError('新业主档案不存在')
    if h['owner_resident_id'] == new_resident_id:
        raise ValueError(f'新业主与当前业主（{h["owner_name"]}）相同，无需过户')
    old_rh = conn.execute(
        "SELECT * FROM resident_house WHERE house_id=? AND rel_type='业主' AND is_current=1",
        (hid,)).fetchone()
    if old_rh:
        conn.execute('UPDATE resident_house SET is_current=0, end_date=? WHERE id=?',
                     (date_str, old_rh['id']))
    conn.execute(
        'INSERT INTO resident_house(resident_id,house_id,rel_type,is_current,start_date,is_living) '
        'VALUES (?,?,?,1,?,1)', (new_resident_id, hid, '业主', date_str))
    new_status = '自住' if h['status'] in ('空置', '装修中') else h['status']
    conn.execute('UPDATE house SET owner_resident_id=?, status=?, checkin_date=? WHERE id=?',
                 (new_resident_id, new_status, date_str, hid))
    conn.commit()
    detail = f'{label_of(h)}：{h["owner_name"] or "（无业主）"} → {new_resident["name"]}'
    log_service.add(conn, h['community_id'], '产权过户', detail)
    return detail


def delete(conn, hid):
    """删除房屋（级联删除其住户关系与全部账单、缴费流水），写入操作日志。"""
    h = get_full(conn, hid)
    if not h:
        raise ValueError('房屋不存在或已被删除')
    bills = conn.execute('SELECT COUNT(*) FROM bill WHERE house_id=?', (hid,)).fetchone()[0]
    conn.execute('DELETE FROM house WHERE id=?', (hid,))
    conn.commit()
    log_service.add(conn, h['community_id'], '删除房屋', f'{label_of(h)}（含账单 {bills} 笔，已级联删除）')


def bill_count(conn, hid):
    return conn.execute('SELECT COUNT(*) FROM bill WHERE house_id=?', (hid,)).fetchone()[0]
