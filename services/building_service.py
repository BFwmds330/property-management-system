# -*- coding: utf-8 -*-
"""楼栋管理业务逻辑。"""


def get(conn, bid):
    return conn.execute('SELECT * FROM building WHERE id=?', (bid,)).fetchone()


def get_by_code(conn, cid, code):
    return conn.execute('SELECT * FROM building WHERE community_id=? AND code=?', (cid, code)).fetchone()


def list_with_count(conn, cid):
    return conn.execute('''
        SELECT b.*, (SELECT COUNT(*) FROM house h WHERE h.building_id=b.id) AS house_count
        FROM building b WHERE b.community_id=? ORDER BY b.id''', (cid,)).fetchall()


def house_count(conn, bid):
    return conn.execute('SELECT COUNT(*) FROM house WHERE building_id=?', (bid,)).fetchone()[0]


def create(conn, cid, data):
    code = (data.get('code') or '').strip()
    if not code:
        raise ValueError('楼栋编号不能为空（如 1#）')
    if len(code) > 20:
        raise ValueError('楼栋编号过长（不超过 20 个字符）')
    if get_by_code(conn, cid, code):
        raise ValueError(f'楼栋「{code}」已存在，编号不可重复')
    cur = conn.execute(
        'INSERT INTO building(community_id,code,unit_count,floors,has_elevator,delivery_status,remark) '
        'VALUES (?,?,?,?,?,?,?)',
        (cid, code, data.get('unit_count') or 1, data.get('floors') or 1,
         1 if data.get('has_elevator') else 0,
         data.get('delivery_status') or '已交付', data.get('remark', '')))
    conn.commit()
    return cur.lastrowid


def update(conn, bid, data):
    row = get(conn, bid)
    if not row:
        raise ValueError('楼栋不存在或已被删除')
    code = (data.get('code') or row['code']).strip()
    if not code:
        raise ValueError('楼栋编号不能为空')
    dup = get_by_code(conn, row['community_id'], code)
    if dup and dup['id'] != bid:
        raise ValueError(f'楼栋「{code}」已存在，编号不可重复')
    conn.execute(
        'UPDATE building SET code=?,unit_count=?,floors=?,has_elevator=?,delivery_status=?,remark=? WHERE id=?',
        (code, data.get('unit_count', row['unit_count']), data.get('floors', row['floors']),
         1 if data.get('has_elevator', row['has_elevator']) else 0,
         data.get('delivery_status', row['delivery_status']),
         data.get('remark', row['remark']), bid))
    conn.commit()


def delete(conn, bid):
    """删除楼栋（级联删除其下房屋、住户关系、账单与缴费流水）。"""
    row = get(conn, bid)
    if not row:
        raise ValueError('楼栋不存在或已被删除')
    conn.execute('DELETE FROM building WHERE id=?', (bid,))
    conn.commit()
    return row['code']
