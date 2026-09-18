# -*- coding: utf-8 -*-
"""统计报表：账期/年度收缴率、欠费 Top 10、各小区收缴率对比。

收缴率 = 实收总额 / 应收总额 * 100%（按账单口径统计：账单归属账期的应收与该账单累计实收）。
"""
from utils.tables import rate_text


def period_summary(conn, cid, period):
    """指定账期：各收费项目的应收/实收/收缴率 + 合计。返回 (分项行, 应收合计, 实收合计)。"""
    rows = conn.execute(
        '''SELECT i.name AS item_name,
                  IFNULL(SUM(b.amount_receivable),0) AS recv,
                  IFNULL(SUM(b.amount_received),0) AS paid
           FROM bill b JOIN fee_item i ON i.id=b.fee_item_id
           WHERE b.community_id=? AND b.period=?
           GROUP BY i.id ORDER BY i.id''', (cid, period)).fetchall()
    recv = sum(r['recv'] for r in rows)
    paid = sum(r['paid'] for r in rows)
    return rows, recv, paid


def year_summary(conn, cid, year):
    """指定年度（账期前缀匹配，兼容月/季/年三种账期格式）。"""
    rows = conn.execute(
        '''SELECT i.name AS item_name,
                  IFNULL(SUM(b.amount_receivable),0) AS recv,
                  IFNULL(SUM(b.amount_received),0) AS paid
           FROM bill b JOIN fee_item i ON i.id=b.fee_item_id
           WHERE b.community_id=? AND b.period LIKE ?
           GROUP BY i.id ORDER BY i.id''', (cid, f'{year}%')).fetchall()
    recv = sum(r['recv'] for r in rows)
    paid = sum(r['paid'] for r in rows)
    return rows, recv, paid


def top_arrears(conn, cid, n=10):
    """欠费金额 Top N 房源（按房屋汇总欠费余额）。"""
    return conn.execute(
        '''SELECT h.id AS hid, bld.code AS bcode, h.unit, h.room_no,
                  r.name AS owner_name, r.phone AS owner_phone,
                  SUM(b.amount_receivable-b.amount_received) AS balance,
                  COUNT(*) AS bill_count
           FROM bill b
           JOIN house h ON h.id=b.house_id
           JOIN building bld ON bld.id=h.building_id
           LEFT JOIN resident r ON r.id=h.owner_resident_id
           WHERE b.community_id=? AND b.amount_receivable>b.amount_received
           GROUP BY h.id ORDER BY balance DESC LIMIT ?''', (cid, n)).fetchall()


def communities_summary(conn, period_prefix):
    """全部小区的应收/实收/收缴率对比（period_prefix 如 '2026-09' 或 '2026'）。"""
    return conn.execute(
        '''SELECT c.id, c.name,
                  IFNULL(SUM(CASE WHEN b.period LIKE ? THEN b.amount_receivable END),0) AS recv,
                  IFNULL(SUM(CASE WHEN b.period LIKE ? THEN b.amount_received END),0) AS paid
           FROM community c
           LEFT JOIN bill b ON b.community_id=c.id
           GROUP BY c.id ORDER BY c.id''',
        (f'{period_prefix}%', f'{period_prefix}%')).fetchall()


def summary_text(recv, paid):
    return f'应收合计 {recv / 100:.2f} 元，实收合计 {paid / 100:.2f} 元，收缴率 {rate_text(recv, paid)}'
