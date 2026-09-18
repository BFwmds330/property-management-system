# -*- coding: utf-8 -*-
"""关键操作日志（删除小区、产权过户、账单调整、备份恢复等均写入）。"""


def add(conn, community_id, action, detail='', operator='系统'):
    conn.execute(
        'INSERT INTO operation_log(community_id, action, detail, operator) VALUES (?,?,?,?)',
        (community_id, action, detail, operator))
    conn.commit()


def recent(conn, limit=50, community_id=None):
    if community_id:
        return conn.execute(
            'SELECT * FROM operation_log WHERE community_id IS NULL OR community_id=? '
            'ORDER BY id DESC LIMIT ?', (community_id, limit)).fetchall()
    return conn.execute(
        'SELECT * FROM operation_log ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
