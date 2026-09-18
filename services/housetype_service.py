# -*- coding: utf-8 -*-
"""户型库管理业务逻辑（户型为小区级，可被多套房屋复用）。"""


def get(conn, tid):
    return conn.execute('SELECT * FROM house_type WHERE id=?', (tid,)).fetchone()


def get_by_name(conn, cid, name):
    return conn.execute('SELECT * FROM house_type WHERE community_id=? AND name=?', (cid, name)).fetchone()


def used_count(conn, tid):
    """引用该户型的房屋数量。"""
    return conn.execute('SELECT COUNT(*) FROM house WHERE house_type_id=?', (tid,)).fetchone()[0]


def list_with_count(conn, cid):
    return conn.execute('''
        SELECT t.*, (SELECT COUNT(*) FROM house h WHERE h.house_type_id=t.id) AS house_count
        FROM house_type t WHERE t.community_id=? ORDER BY t.id''', (cid,)).fetchall()


def create(conn, cid, data):
    name = (data.get('name') or '').strip()
    if not name:
        raise ValueError('户型名称不能为空（如：三室两厅两卫 A 户型）')
    if get_by_name(conn, cid, name):
        raise ValueError(f'户型「{name}」已存在')
    cur = conn.execute(
        'INSERT INTO house_type(community_id,name,rooms,halls,baths,area,orientation,'
        'has_balcony,has_bay_window,has_garden,remark) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (cid, name, data.get('rooms') or 1, data.get('halls') or 1, data.get('baths') or 1,
         data.get('area') or 0, data.get('orientation') or '南',
         1 if data.get('has_balcony') else 0, 1 if data.get('has_bay_window') else 0,
         1 if data.get('has_garden') else 0, data.get('remark', '')))
    conn.commit()
    return cur.lastrowid


def update(conn, tid, data):
    row = get(conn, tid)
    if not row:
        raise ValueError('户型不存在或已被删除')
    name = (data.get('name') or row['name']).strip()
    if not name:
        raise ValueError('户型名称不能为空')
    dup = get_by_name(conn, row['community_id'], name)
    if dup and dup['id'] != tid:
        raise ValueError(f'户型「{name}」已存在')
    conn.execute(
        'UPDATE house_type SET name=?,rooms=?,halls=?,baths=?,area=?,orientation=?,'
        'has_balcony=?,has_bay_window=?,has_garden=?,remark=? WHERE id=?',
        (name, data.get('rooms', row['rooms']), data.get('halls', row['halls']),
         data.get('baths', row['baths']), data.get('area', row['area']),
         data.get('orientation', row['orientation']),
         1 if data.get('has_balcony', row['has_balcony']) else 0,
         1 if data.get('has_bay_window', row['has_bay_window']) else 0,
         1 if data.get('has_garden', row['has_garden']) else 0,
         data.get('remark', row['remark']), tid))
    conn.commit()
    return used_count(conn, tid)


def delete(conn, tid):
    """删除户型（被房屋引用时禁止删除，避免房屋悬空）。"""
    row = get(conn, tid)
    if not row:
        raise ValueError('户型不存在或已被删除')
    n = used_count(conn, tid)
    if n:
        raise ValueError(f'该户型已被 {n} 套房屋引用，不能删除；可先修改这些房屋的户型')
    conn.execute('DELETE FROM house_type WHERE id=?', (tid,))
    conn.commit()


def distribution(conn, cid):
    """户型分布统计：各户型的房屋数量（含未设置户型）。"""
    rows = conn.execute('''
        SELECT t.name AS name, COUNT(h.id) AS cnt
        FROM house_type t LEFT JOIN house h ON h.house_type_id=t.id
        WHERE t.community_id=? GROUP BY t.id ORDER BY cnt DESC''', (cid,)).fetchall()
    none_cnt = conn.execute(
        'SELECT COUNT(*) FROM house WHERE community_id=? AND house_type_id IS NULL', (cid,)).fetchone()[0]
    if none_cnt:
        rows = list(rows) + [{'name': '（未设置户型）', 'cnt': none_cnt}]
    return rows
