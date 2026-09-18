# -*- coding: utf-8 -*-
"""小区管理业务逻辑。"""


def count(conn):
    return conn.execute('SELECT COUNT(*) FROM community').fetchone()[0]


def get(conn, cid):
    return conn.execute('SELECT * FROM community WHERE id=?', (cid,)).fetchone()


def get_by_name(conn, name):
    return conn.execute('SELECT * FROM community WHERE name=?', (name,)).fetchone()


def all(conn):
    return conn.execute('SELECT * FROM community ORDER BY id').fetchall()


def create(conn, data):
    name = (data.get('name') or '').strip()
    if not name:
        raise ValueError('小区名称不能为空')
    if get_by_name(conn, name):
        raise ValueError(f'小区「{name}」已存在，名称不可重复')
    cur = conn.execute(
        'INSERT INTO community(name,address,area_land,area_building,green_rate,plan_buildings,'
        'parking_total,delivery_date,takeover_date,service_phone,remark) '
        'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (name, data.get('address', ''), data.get('area_land') or 0, data.get('area_building') or 0,
         data.get('green_rate') or 0, data.get('plan_buildings') or 0, data.get('parking_total') or 0,
         data.get('delivery_date', ''), data.get('takeover_date', ''), data.get('service_phone', ''),
         data.get('remark', '')))
    conn.commit()
    return cur.lastrowid


def update(conn, cid, data):
    row = get(conn, cid)
    if not row:
        raise ValueError('小区不存在或已被删除')
    name = (data.get('name') or '').strip()
    if not name:
        raise ValueError('小区名称不能为空')
    dup = get_by_name(conn, name)
    if dup and dup['id'] != cid:
        raise ValueError(f'小区「{name}」已存在，名称不可重复')
    conn.execute(
        'UPDATE community SET name=?,address=?,area_land=?,area_building=?,green_rate=?,'
        'plan_buildings=?,parking_total=?,delivery_date=?,takeover_date=?,service_phone=?,remark=? '
        'WHERE id=?',
        (name, data.get('address', row['address']),
         data.get('area_land', row['area_land']), data.get('area_building', row['area_building']),
         data.get('green_rate', row['green_rate']), data.get('plan_buildings', row['plan_buildings']),
         data.get('parking_total', row['parking_total']), data.get('delivery_date', row['delivery_date']),
         data.get('takeover_date', row['takeover_date']), data.get('service_phone', row['service_phone']),
         data.get('remark', row['remark']), cid))
    conn.commit()


def delete(conn, cid):
    """硬删除小区，外键级联清理楼栋/房屋/住户关系/账单/缴费流水等全部数据。"""
    row = get(conn, cid)
    if not row:
        raise ValueError('小区不存在或已被删除')
    conn.execute('DELETE FROM community WHERE id=?', (cid,))
    conn.commit()
    return row['name']


def search(conn, kw):
    like = f'%{kw}%'
    return conn.execute(
        'SELECT * FROM community WHERE name LIKE ? OR address LIKE ? ORDER BY id',
        (like, like)).fetchall()


def list_stats(conn):
    """小区列表 + 汇总信息（楼栋数/房屋数/在住人数/当前欠费总额）。"""
    return conn.execute('''
        SELECT c.*,
          (SELECT COUNT(*) FROM building b WHERE b.community_id=c.id) AS building_count,
          (SELECT COUNT(*) FROM house h WHERE h.community_id=c.id) AS house_count,
          (SELECT COUNT(DISTINCT rh.resident_id) FROM resident_house rh
             JOIN house h2 ON h2.id=rh.house_id
            WHERE h2.community_id=c.id AND rh.is_current=1) AS resident_count,
          (SELECT IFNULL(SUM(b.amount_receivable-b.amount_received),0) FROM bill b
            WHERE b.community_id=c.id AND b.status!='已缴清') AS arrears
        FROM community c ORDER BY c.id''').fetchall()
