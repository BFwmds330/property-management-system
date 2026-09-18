# -*- coding: utf-8 -*-
"""住户业务：业主入住、家庭成员、租户登记、搬出退租、历史轨迹、搜索与通讯录。"""
from services.house_service import label_of
from utils.dates import days_until


def get(conn, rid):
    return conn.execute('SELECT * FROM resident WHERE id=?', (rid,)).fetchone()


def add_person(conn, data):
    name = (data.get('name') or '').strip()
    if not name:
        raise ValueError('姓名不能为空')
    cur = conn.execute(
        'INSERT INTO resident(name,gender,birth_date,id_type,id_number,phone,wechat,workplace,'
        'emergency_contact,emergency_phone,remark) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (name, data.get('gender') or '保密', data.get('birth_date', ''),
         data.get('id_type') or '身份证', data.get('id_number', ''), data.get('phone', ''),
         data.get('wechat', ''), data.get('workplace', ''), data.get('emergency_contact', ''),
         data.get('emergency_phone', ''), data.get('remark', '')))
    conn.commit()
    return cur.lastrowid


def update_person(conn, rid, data):
    row = get(conn, rid)
    if not row:
        raise ValueError('住户档案不存在')
    conn.execute(
        'UPDATE resident SET name=?,gender=?,birth_date=?,id_type=?,id_number=?,phone=?,wechat=?,'
        'workplace=?,emergency_contact=?,emergency_phone=?,remark=? WHERE id=?',
        ((data.get('name') or row['name']).strip(), data.get('gender', row['gender']),
         data.get('birth_date', row['birth_date']), data.get('id_type', row['id_type']),
         data.get('id_number', row['id_number']), data.get('phone', row['phone']),
         data.get('wechat', row['wechat']), data.get('workplace', row['workplace']),
         data.get('emergency_contact', row['emergency_contact']),
         data.get('emergency_phone', row['emergency_phone']),
         data.get('remark', row['remark']), rid))
    conn.commit()


def current_link(conn, house_id, rel_type):
    return conn.execute(
        'SELECT rh.*, r.name AS rname FROM resident_house rh '
        'JOIN resident r ON r.id=rh.resident_id '
        'WHERE rh.house_id=? AND rh.rel_type=? AND rh.is_current=1',
        (house_id, rel_type)).fetchone()


def link(conn, house_id, resident_id, rel_type, *, relation='', start_date='', is_living=1,
         rent_start='', rent_end='', rent_monthly=None, remark=''):
    """建立住户-房屋关系。业主/租户同一时间各仅允许一名在住。"""
    if rel_type == '业主':
        exist = current_link(conn, house_id, '业主')
        if exist:
            raise ValueError(f'该房屋已有业主（{exist["rname"]}），如需更换请使用"产权过户"功能')
    if rel_type == '租户':
        exist = current_link(conn, house_id, '租户')
        if exist:
            raise ValueError(f'该房屋已有在租租户（{exist["rname"]}），请先办理退租')
    cur = conn.execute(
        'INSERT INTO resident_house(resident_id,house_id,rel_type,relation,is_current,start_date,'
        'is_living,rent_start,rent_end,rent_monthly,remark) VALUES (?,?,?,?,1,?,?,?,?,?,?)',
        (resident_id, house_id, rel_type, relation, start_date, is_living,
         rent_start, rent_end, rent_monthly, remark))
    if rel_type == '业主':
        conn.execute(
            "UPDATE house SET owner_resident_id=?, status=CASE WHEN status='空置' THEN '自住' "
            'ELSE status END, checkin_date=? WHERE id=?',
            (resident_id, start_date, house_id))
    conn.commit()
    return cur.lastrowid


def list_of_house(conn, house_id, current_only=True):
    sql = ('SELECT rh.*, r.name, r.gender, r.phone, r.id_type, r.id_number, r.workplace, '
           'r.emergency_contact, r.emergency_phone, r.wechat, r.birth_date, r.remark AS person_remark '
           'FROM resident_house rh JOIN resident r ON r.id=rh.resident_id WHERE rh.house_id=?')
    if current_only:
        sql += ' AND rh.is_current=1'
    sql += " ORDER BY CASE rh.rel_type WHEN '业主' THEN 0 WHEN '家庭成员' THEN 1 ELSE 2 END, rh.id"
    return conn.execute(sql, (house_id,)).fetchall()


def history_of_house(conn, house_id):
    return conn.execute(
        'SELECT rh.*, r.name, r.phone FROM resident_house rh '
        'JOIN resident r ON r.id=rh.resident_id WHERE rh.house_id=? ORDER BY rh.id',
        (house_id,)).fetchall()


def move_out(conn, rh_id, end_date):
    """搬出/退租：关系记录转历史。业主搬出同时清空房屋产权人并置为空置。"""
    row = conn.execute(
        'SELECT rh.*, r.name AS rname FROM resident_house rh '
        'JOIN resident r ON r.id=rh.resident_id WHERE rh.id=?', (rh_id,)).fetchone()
    if not row or not row['is_current']:
        raise ValueError('该记录不是在住记录，无法办理搬出')
    conn.execute('UPDATE resident_house SET is_current=0, end_date=? WHERE id=?', (end_date, rh_id))
    if row['rel_type'] == '业主':
        conn.execute(
            "UPDATE house SET owner_resident_id=NULL, status='空置' "
            'WHERE id=? AND owner_resident_id=?', (row['house_id'], row['resident_id']))
    conn.commit()
    return row


def search_residents(conn, cid, kw):
    """全局搜索当前在住住户：姓名/手机号/房号。"""
    like = f'%{kw}%'
    return conn.execute(
        '''SELECT rh.*, r.name, r.gender, r.phone, r.id_number, h.room_no, h.unit, b.code AS bcode
           FROM resident_house rh
           JOIN resident r ON r.id=rh.resident_id
           JOIN house h ON h.id=rh.house_id
           JOIN building b ON b.id=h.building_id
           WHERE h.community_id=? AND rh.is_current=1
             AND (r.name LIKE ? OR r.phone LIKE ? OR h.room_no LIKE ? OR b.code LIKE ?)
           ORDER BY r.name LIMIT 100''',
        (cid, like, like, like, like)).fetchall()


def search_plain(conn, cid, kw, limit=20):
    """按姓名/手机号搜索小区内住户档案（用于过户选择新业主）。"""
    like = f'%{kw}%'
    return conn.execute(
        '''SELECT DISTINCT r.* FROM resident r
           JOIN resident_house rh ON rh.resident_id=r.id
           JOIN house h ON h.id=rh.house_id
           WHERE h.community_id=? AND (r.name LIKE ? OR r.phone LIKE ?)
           ORDER BY r.name LIMIT ?''',
        (cid, like, like, limit)).fetchall()


def directory_rows(conn, cid):
    """当前小区全部在住住户通讯录（导出 CSV 用）。"""
    rows = conn.execute(
        '''SELECT rh.*, r.name, r.gender, r.phone, r.id_type, r.id_number, r.wechat, r.workplace,
                  r.emergency_contact, r.emergency_phone, b.code AS bcode, h.unit, h.room_no
           FROM resident_house rh
           JOIN resident r ON r.id=rh.resident_id
           JOIN house h ON h.id=rh.house_id
           JOIN building b ON b.id=h.building_id
           WHERE h.community_id=? AND rh.is_current=1
           ORDER BY b.id, h.unit, h.room_no,
                    CASE rh.rel_type WHEN '业主' THEN 0 WHEN '家庭成员' THEN 1 ELSE 2 END, rh.id''',
        (cid,)).fetchall()
    out = []
    for r in rows:
        out.append([
            label_of(r), r['rel_type'], r['relation'], r['name'], r['gender'],
            r['phone'], f"{r['id_type']} {r['id_number']}", r['wechat'], r['workplace'],
            r['emergency_contact'], r['emergency_phone'],
            '是' if r['is_living'] else '否', r['start_date'],
            r['rent_end'], r['rent_monthly'], r['remark'],
        ])
    return out


def lease_expiring(conn, cid, remind_days=30):
    """30 天内到期（或已过期未退租）的在租租约。"""
    rows = conn.execute(
        '''SELECT rh.*, r.name, r.phone, h.room_no, h.unit, b.code AS bcode
           FROM resident_house rh
           JOIN resident r ON r.id=rh.resident_id
           JOIN house h ON h.id=rh.house_id
           JOIN building b ON b.id=h.building_id
           WHERE h.community_id=? AND rh.is_current=1 AND rh.rel_type='租户'
             AND rh.rent_end!='' ORDER BY rh.rent_end''', (cid,)).fetchall()
    return [r for r in rows if days_until(r['rent_end']) is not None
            and days_until(r['rent_end']) <= remind_days]
