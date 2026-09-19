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


def vehicle_stats(conn, cid, period=''):
    """每户车辆信息统计。

    返回 {'rows': [每户明细], 'summary': 汇总}。period 非空时附带该账期车位费
    （按车位分缴账单）的缴纳情况。
    明细字段：house_id、house_label、owner_name、tenant_name、vehicles（车牌车位明细文本）、
    vehicle_count、parking_fee_paid、parking_fee_unpaid、parking_fee_arrears（分）。
    """
    houses = conn.execute(
        '''SELECT h.*, b.code AS bcode, o.name AS owner_name,
                  (SELECT r.name FROM resident_house rh JOIN resident r ON r.id=rh.resident_id
                    WHERE rh.house_id=h.id AND rh.rel_type='租户' AND rh.is_current=1 LIMIT 1)
                    AS tenant_name
           FROM house h
           JOIN building b ON b.id=h.building_id
           LEFT JOIN resident o ON o.id=h.owner_resident_id
           WHERE h.community_id=?
           ORDER BY b.id, h.unit, h.floor, h.room_no''', (cid,)).fetchall()
    vehicles = {}
    for v in conn.execute(
            '''SELECT v.* FROM vehicle v JOIN house h ON h.id=v.house_id
               WHERE h.community_id=? ORDER BY v.id''', (cid,)):
        vehicles.setdefault(v['house_id'], []).append(v)
    fee = {}
    if period:
        for r in conn.execute(
                '''SELECT b.house_id, b.status,
                          b.amount_receivable - b.amount_received AS balance
                   FROM bill b JOIN fee_item i ON i.id=b.fee_item_id
                   WHERE b.community_id=? AND b.period=? AND i.pricing_type='按车位' ''',
                (cid, period)):
            fee.setdefault(r['house_id'], []).append(r)
    from services.house_service import label_of
    rows = []
    for h in houses:
        vs = vehicles.get(h['id'], [])
        detail = '、'.join(
            f"{v['plate']}" + (f"（{v['slot_no']}）" if v['slot_no'] else '') for v in vs)
        bills = fee.get(h['id'], [])
        rows.append({
            'house_id': h['id'],
            'house_label': label_of(h),
            'owner_name': h['owner_name'] or '-',
            'tenant_name': h['tenant_name'] or '-',
            'vehicle_count': len(vs),
            'vehicles': detail,
            'parking_fee_paid': sum(1 for b in bills if b['status'] == '已缴清'),
            'parking_fee_unpaid': sum(1 for b in bills if b['status'] != '已缴清'),
            'parking_fee_arrears': sum(b['balance'] for b in bills if b['status'] != '已缴清'),
        })
    summary = {
        'total_vehicles': sum(r['vehicle_count'] for r in rows),
        'houses_with_vehicle': sum(1 for r in rows if r['vehicle_count'] > 0),
        'houses_without_vehicle': sum(1 for r in rows if r['vehicle_count'] == 0),
        'parking_fee_arrears': sum(r['parking_fee_arrears'] for r in rows),
        'period': period,
    }
    return {'rows': rows, 'summary': summary}


def summary_text(recv, paid):
    return f'应收合计 {recv / 100:.2f} 元，实收合计 {paid / 100:.2f} 元，收缴率 {rate_text(recv, paid)}'
