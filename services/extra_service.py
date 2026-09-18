# -*- coding: utf-8 -*-
"""扩展功能：小区公告、报修登记、车辆信息。"""
from utils.dates import today_str


# ---------- 公告 ----------

def announcements(conn, cid):
    return conn.execute(
        'SELECT * FROM announcement WHERE community_id=? ORDER BY publish_date DESC, id DESC',
        (cid,)).fetchall()


def get_announcement(conn, aid):
    return conn.execute('SELECT * FROM announcement WHERE id=?', (aid,)).fetchone()


def add_announcement(conn, cid, title, content, publish_date):
    if not (title or '').strip():
        raise ValueError('公告标题不能为空')
    conn.execute('INSERT INTO announcement(community_id,title,content,publish_date) VALUES (?,?,?,?)',
                 (cid, title.strip(), content or '', publish_date or today_str()))
    conn.commit()


def update_announcement(conn, aid, title, content, publish_date):
    if not (title or '').strip():
        raise ValueError('公告标题不能为空')
    conn.execute('UPDATE announcement SET title=?,content=?,publish_date=? WHERE id=?',
                 (title.strip(), content or '', publish_date, aid))
    conn.commit()


def delete_announcement(conn, aid):
    conn.execute('DELETE FROM announcement WHERE id=?', (aid,))
    conn.commit()


# ---------- 报修 ----------

def repairs(conn, cid, status=''):
    sql = ('SELECT rp.*, h.room_no, h.unit, b.code AS bcode FROM repair rp '
           'JOIN house h ON h.id=rp.house_id JOIN building b ON b.id=h.building_id '
           'WHERE rp.community_id=?')
    args = [cid]
    if status:
        sql += ' AND rp.status=?'
        args.append(status)
    sql += ' ORDER BY rp.id DESC'
    return conn.execute(sql, args).fetchall()


def get_repair(conn, rid):
    return conn.execute('SELECT * FROM repair WHERE id=?', (rid,)).fetchone()


def add_repair(conn, cid, house_id, content):
    if not (content or '').strip():
        raise ValueError('报修内容不能为空')
    cur = conn.execute('INSERT INTO repair(community_id,house_id,content) VALUES (?,?,?)',
                       (cid, house_id, content.strip()))
    conn.commit()
    return cur.lastrowid


def update_repair(conn, rid, status, handler='', result=''):
    """状态流转：待处理 -> 处理中 -> 已完成（填写已完成时自动记录完成时间）。"""
    if status not in ('待处理', '处理中', '已完成'):
        raise ValueError('报修状态不合法')
    finished = today_str() if status == '已完成' else ''
    conn.execute(
        'UPDATE repair SET status=?, handler=?, result=?, '
        "finished_at=CASE WHEN ?='已完成' THEN ? ELSE finished_at END WHERE id=?",
        (status, handler, result, status, finished, rid))
    conn.commit()


# ---------- 车辆 ----------

def vehicles_of(conn, house_id):
    return conn.execute('SELECT * FROM vehicle WHERE house_id=? ORDER BY id', (house_id,)).fetchall()


def add_vehicle(conn, house_id, plate, slot_no='', remark=''):
    plate = (plate or '').strip().upper().replace(' ', '').replace('·', '')
    if not plate:
        raise ValueError('车牌号不能为空')
    if len(plate) < 6 or len(plate) > 8:
        raise ValueError('车牌号格式不正确（如 京A12345）')
    conn.execute('INSERT INTO vehicle(house_id,plate,slot_no,remark) VALUES (?,?,?,?)',
                 (house_id, plate, slot_no.strip(), remark))
    conn.commit()


def delete_vehicle(conn, vid):
    conn.execute('DELETE FROM vehicle WHERE id=?', (vid,))
    conn.commit()
