# -*- coding: utf-8 -*-
"""端到端冒烟测试：用临时数据库覆盖交付验收标准的全部核心场景。

运行：python tests/smoke_test.py
不依赖终端交互，直接调用服务层；交互健壮性另由交互测试保证。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['PROPERTY_DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'smoke.db')

import db  # noqa: E402
from services import (building_service as bs, community_service as cs,  # noqa: E402
                      demo_data, extra_service as es, fee_service as fs,
                      house_service as hs, housetype_service as ts,
                      log_service, resident_service as rs)
from services import report_service as rpt  # noqa: E402
from utils import exporter  # noqa: E402
from utils.validators import (check_id_card, check_money, check_phone,  # noqa: E402
                              check_period)

checks = []


def check(name, cond, extra=''):
    checks.append((name, bool(cond)))
    print(('  [通过] ' if cond else '  [失败] ') + name + (f'   {extra}' if extra and not cond else ''))


def make_id(body17):
    w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    ck = '10X98765432'
    return body17 + ck[sum(int(c) * x for c, x in zip(body17, w)) % 11]


VALID_ID = make_id('11010519900101123')

conn = db.connect()

print('\n== 1. 演示数据 / 多小区与数据隔离 ==')
msg = demo_data.load_demo(conn)
print('  ' + msg)
stats = cs.list_stats(conn)
check('演示数据含 2 个小区', len(stats) == 2)
check('每小区房屋数 ≥ 30', all(s['house_count'] >= 30 for s in stats),
      f"{[s['house_count'] for s in stats]}")
check('每小区在住人数 ≥ 20', all(s['resident_count'] >= 20 for s in stats),
      f"{[s['resident_count'] for s in stats]}")
check('演示数据含欠费（用于欠费演示）', all(s['arrears'] > 0 for s in stats))
c1, c2 = stats[0], stats[1]

cid2 = c2['id']
bid = bs.create(conn, cid2, dict(code='T9', unit_count=1, floors=2, has_elevator=False))
check('新增楼栋（小区2）', bid > 0)

print('\n== 2. 批量生成房屋并绑定户型 ==')
tid = ts.create(conn, cid2, dict(name='测试三室', rooms=3, halls=2, baths=2, area=120.0,
                                 orientation='南', has_balcony=1))
created, skipped = hs.batch_generate(conn, cid2, bs.get(conn, bid), 1, 1, 2, 4, tid, None, None)
check('批量生成 1 单元 2 层每层 4 户 = 8 套', created == 8, f'created={created}')
again, again_skip = hs.batch_generate(conn, cid2, bs.get(conn, bid), 1, 1, 2, 4, tid, None, None)
check('重复生成自动跳过已存在房屋', again == 0 and again_skip == 8)
rows_by_room = [r for r in hs.search(conn, cid2, kw='101') if r['bcode'] == 'T9']
check('按房号可检索到生成的房屋', len(rows_by_room) == 1 and rows_by_room[0]['room_no'] == '101')
h = rows_by_room[0]
check('生成房屋已绑定户型', h['house_type_id'] == tid and h['tname'] == '测试三室')

print('\n== 3. 住户：业主 + 2 名成员 + 1 名租户 ==')
hid = h['id']
oid = rs.add_person(conn, dict(name='测试业主', gender='男', id_type='身份证',
                               id_number=VALID_ID, phone='13812345678'))
rs.link(conn, hid, oid, '业主', start_date='2026-01-01')
m1 = rs.add_person(conn, dict(name='测试成员一', gender='女', phone='13912345678'))
m2 = rs.add_person(conn, dict(name='测试成员二', phone='13712345678'))
rs.link(conn, hid, m1, '家庭成员', relation='配偶')
rs.link(conn, hid, m2, '家庭成员', relation='子女')
tn = rs.add_person(conn, dict(name='测试租户', phone='13612345678'))
rs.link(conn, hid, tn, '租户', rent_start='2026-01-01', rent_end='2026-03-01', rent_monthly=3000.0)
cur = rs.list_of_house(conn, hid)
check('房屋当前住户 = 1 业主 + 2 成员 + 1 租户', len(cur) == 4, f'{len(cur)}')
hs.set_status(conn, hid, '出租')
expiring = rs.lease_expiring(conn, cid2, 400)
check('租约到期提醒可检索到该租约', any(r['name'] == '测试租户' for r in expiring))

print('\n== 4. 账单生成 / 部分缴费 / 全额缴费 / 状态流转 ==')
fid = fs.create_item(conn, cid2, dict(name='测试物业费', pricing_type='面积单价',
                                      unit_price=2.0, period_type='月', enabled=True))
item = fs.get_item(conn, fid)
created, skipped, total = fs.generate(conn, cid2, item, '2026-09')
bill = [b for b in fs.bills_query(conn, cid2, period='2026-09') if b['house_id'] == hid][0]
expect = round(h['area_gross'] * 2.0 * 100)
check('账单金额 = 单价 × 建筑面积', bill['amount_receivable'] == expect,
      f"{bill['amount_receivable']} vs {expect}")
check('初始状态为未缴', bill['status'] == '未缴')
part = expect // 3
fs.pay(conn, bill['id'], part, '2026-09-10', '现金', 'R001', '测试员')
b1 = fs.get_bill(conn, bill['id'])
check('部分缴费后状态 = 部分缴纳', b1['status'] == '部分缴纳')
fs.pay(conn, bill['id'], expect - part, '2026-09-15', '扫码', 'R002', '测试员')
b2 = fs.get_bill(conn, bill['id'])
check('缴清后状态 = 已缴清', b2['status'] == '已缴清')
try:
    fs.pay(conn, bill['id'], 100, '2026-09-16', '现金', 'R003', '测试员')
    check('已缴清账单拒绝再缴费', False)
except ValueError:
    check('已缴清账单拒绝再缴费', True)

print('\n== 5. 报表数字与手工核算一致 ==')
# 受控场景：新小区 1 套房 100㎡、单价 2 元/㎡/月 -> 2026-08 应收 200 元，实缴 50 元
cid3 = cs.create(conn, dict(name='核算小区'))
bid3 = bs.create(conn, cid3, dict(code='1#', unit_count=1, floors=1))
hid3 = hs.create(conn, cid3, dict(building_id=bid3, unit=1, floor=1, room_no='101',
                                  area_gross=100.0, area_inner=78.0))
fid3 = fs.create_item(conn, cid3, dict(name='物业费', pricing_type='面积单价',
                                       unit_price=2.0, period_type='月', enabled=True))
fs.generate(conn, cid3, fs.get_item(conn, fid3), '2026-08')
bill3 = [b for b in fs.bills_query(conn, cid3, period='2026-08')][0]
fs.pay(conn, bill3['id'], 5000, '2026-08-20', '现金', 'R100', '测试员')  # 50 元
rrows, recv, paid = rpt.period_summary(conn, cid3, '2026-08')
check('账期应收 = 200.00 元', recv == 20000, f'{recv}')
check('账期实收 = 50.00 元', paid == 5000, f'{paid}')
check('收缴率 = 实收/应收 = 25%', abs(paid / recv * 100 - 25.0) < 1e-9)
arr = fs.arrears_rows(conn, cid3)
check('欠费清单余额 = 150.00 元', len(arr) == 1 and arr[0]['balance'] == 15000, f'{arr}')
yrows, yrecv, ypaid = rpt.year_summary(conn, cid3, '2026')
check('年度报表口径与账期一致', yrecv == 20000 and ypaid == 5000)

print('\n== 6. 欠费调整（减免留痕）与操作日志 ==')
detail = fs.adjust(conn, bill3['id'], 10000, '业主疫情减免')
check('账单调整后应收 = 100.00 元', fs.get_bill(conn, bill3['id'])['amount_receivable'] == 10000)
logs = log_service.recent(conn, 50, cid3)
check('账单调整已写入操作日志', any(l['action'] == '账单调整' for l in logs))

print('\n== 7. 产权过户留痕 ==')
new_owner = rs.add_person(conn, dict(name='新业主', phone='13512345678'))
detail = hs.transfer(conn, hid, new_owner, '2026-09-18')
hist = rs.history_of_house(conn, hid)
owner_rows = [x for x in hist if x['rel_type'] == '业主']
check('过户后产生新旧两条业主记录', len(owner_rows) == 2)
check('旧业主记录已转历史（is_current=0 且有 end_date）',
      any(x['is_current'] == 0 and x['end_date'] == '2026-09-18' for x in owner_rows))
check('当前业主已更新为新业主', hs.get_full(conn, hid)['owner_resident_id'] == new_owner)
logs = log_service.recent(conn, 50, cid2)
check('过户已写入操作日志', any(l['action'] == '产权过户' for l in logs))

print('\n== 8. CSV 导出 ==')
dir_rows = rs.directory_rows(conn, cid2)
p1 = exporter.export_csv('测试_住户通讯录', ['房号', '姓名'], dir_rows[:5])
arr_data = [[1, 2]] 
p2 = exporter.export_csv('测试_催缴单', ['a', 'b'], arr_data)
check('住户通讯录与催缴单 CSV 导出成功',
      os.path.exists(p1) and os.path.getsize(p1) > 0 and os.path.exists(p2) and os.path.getsize(p2) > 0)

print('\n== 9. 重启后数据不丢失 ==')
house_count_before = hs.count_all(conn, cid2)
conn.close()
conn = db.connect()
check('重连数据库后小区数量不变', cs.count(conn) == 3)
check('重连数据库后房屋数量不变', hs.count_all(conn, cid2) == house_count_before)
check('重连数据库后缴费流水仍在',
      conn.execute('SELECT COUNT(*) FROM payment WHERE community_id=?', (cid3,)).fetchone()[0] == 1)

print('\n== 10. 输入校验 ==')
check('身份证 18 位校验位验证通过', check_id_card(VALID_ID)[0])
bad_id = VALID_ID[:17] + ('0' if VALID_ID[17] != '0' else '1')
check('身份证校验位错误被拒绝', not check_id_card(bad_id)[0])
check('手机号格式校验', check_phone('13812345678')[0] and not check_phone('12345')[0])
check('账期格式校验（月/季/年）',
      check_period('2026-09', '月')[0] and check_period('2026-Q3', '季')[0]
      and check_period('2026', '年')[0] and not check_period('2026-13', '月')[0])
check('金额转分（两位小数、拒绝负数与三位小数）',
      check_money('350.5')[1] == 35050 and not check_money('-1')[0]
      and not check_money('1.234')[0])

print('\n== 11. 车位费按车位分缴 ==')
es.add_vehicle(conn, hid3, '京A11111', 'D001')
es.add_vehicle(conn, hid3, '京B22222', 'D002')
fidp = fs.create_item(conn, cid3, dict(name='车位费', pricing_type='按车位',
                                       fixed_amount=150.0, period_type='月', enabled=True))
created, skipped, total = fs.generate(conn, cid3, fs.get_item(conn, fidp), '2026-09')
check('两个车位各生成一张账单（每张 150 元）', created == 2 and total == 30000,
      f'created={created}, total={total}')
slot_bills = [b for b in fs.bills_query(conn, cid3, period='2026-09')
              if b['item_name'] == '车位费']
check('两张账单车位标识互不相同', len(slot_bills) == 2
      and len({b['unit_no'] for b in slot_bills}) == 2)
check('车位账单展示含车位标识',
      all('车位' in fs.bill_room_label(b) for b in slot_bills))
fs.pay(conn, slot_bills[0]['id'], 15000, '2026-09-10', '现金', 'P1', '测试员')
fs.pay(conn, slot_bills[1]['id'], 5000, '2026-09-11', '现金', 'P2', '测试员')
check('车位1全额缴清、车位2部分缴纳（分缴独立）',
      fs.get_bill(conn, slot_bills[0]['id'])['status'] == '已缴清'
      and fs.get_bill(conn, slot_bills[1]['id'])['status'] == '部分缴纳')
arr = fs.arrears_rows(conn, cid3)
check('欠费清单按车位分列（车位2欠 100 元）',
      any(a['bill']['id'] == slot_bills[1]['id'] and a['balance'] == 10000 for a in arr))
# 再次生成同账期：跳过已存在，不重复计费
again, again_skip, _ = fs.generate(conn, cid3, fs.get_item(conn, fidp), '2026-09')
check('重复生成车位费自动跳过', again == 0 and again_skip == 2)

print('\n== 12. 删除未缴账单 ==')
try:
    fs.delete_bill(conn, slot_bills[1]['id'])
    check('有缴费记录的账单拒绝删除', False)
except ValueError:
    check('有缴费记录的账单拒绝删除',
          fs.get_bill(conn, slot_bills[1]['id']) is not None)
try:
    fs.delete_bill(conn, slot_bills[0]['id'])
    check('已缴清账单拒绝删除', False)
except ValueError:
    check('已缴清账单拒绝删除', True)
fid4 = fs.create_item(conn, cid3, dict(name='临时清洁费', pricing_type='按户固定',
                                       fixed_amount=10.0, period_type='月', enabled=True))
fs.generate(conn, cid3, fs.get_item(conn, fid4), '2026-09')
tmp_bill = [b for b in fs.bills_query(conn, cid3, period='2026-09')
            if b['item_name'] == '临时清洁费'][0]
fs.delete_bill(conn, tmp_bill['id'])
check('无缴费记录的未缴账单可删除', fs.get_bill(conn, tmp_bill['id']) is None)
logs = log_service.recent(conn, 50, cid3)
check('删除账单已写入操作日志', any(l['action'] == '删除账单' for l in logs))

print('\n== 13. 每户车辆统计 ==')
stats = rpt.vehicle_stats(conn, cid3, '2026-09')
row3 = [r for r in stats['rows'] if r['house_id'] == hid3][0]
check('每户车辆数 = 2', row3['vehicle_count'] == 2)
check('车牌车位明细完整', '京A11111' in row3['vehicles'] and 'D002' in row3['vehicles'])
check('本期车位费：缴清 1 笔 / 未缴 1 笔（部分缴纳仍计未缴）',
      row3['parking_fee_paid'] == 1 and row3['parking_fee_unpaid'] == 1,
      f"paid={row3['parking_fee_paid']}, unpaid={row3['parking_fee_unpaid']}")
check('车位费欠费合计 = 100 元（150 应收 - 50 已缴）',
      row3['parking_fee_arrears'] == 10000, f"{row3['parking_fee_arrears']}")
check('统计汇总车辆数 = 2，有车 1 户',
      stats['summary']['total_vehicles'] == 2
      and stats['summary']['houses_with_vehicle'] == 1)
stats_no_period = rpt.vehicle_stats(conn, cid3)
check('不带账期仅统计车辆信息',
      stats_no_period['summary']['total_vehicles'] == 2
      and stats_no_period['rows'][0]['parking_fee_paid'] == 0)

print('\n== 14. 旧库迁移（账单表增加 unit_no）==')
import sqlite3 as _sq  # noqa: E402
legacy_path = os.path.join(tempfile.mkdtemp(), 'legacy.db')
c2 = _sq.connect(legacy_path)
c2.row_factory = _sq.Row
c2.execute('''CREATE TABLE bill (
  id INTEGER PRIMARY KEY AUTOINCREMENT, community_id INTEGER NOT NULL, house_id INTEGER NOT NULL,
  fee_item_id INTEGER NOT NULL, period TEXT NOT NULL, original_amount INTEGER NOT NULL,
  adjust_amount INTEGER NOT NULL DEFAULT 0, amount_receivable INTEGER NOT NULL,
  amount_received INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT '未缴',
  adjust_reason TEXT NOT NULL DEFAULT '', created_at TEXT,
  UNIQUE (house_id, fee_item_id, period))''')
c2.execute("INSERT INTO bill(community_id, house_id, fee_item_id, period, original_amount, "
           "amount_receivable, status, created_at) "
           "VALUES (1, 1, 1, '2026-08', 10000, 10000, '未缴', '2026-08-01 10:00:00')")
c2.commit()
check('迁移前无 unit_no 列', 'unit_no' not in [r[1] for r in c2.execute('PRAGMA table_info(bill)')])
changed = db.migrate(c2)
cols = [r[1] for r in c2.execute('PRAGMA table_info(bill)')]
check('迁移后账单表包含 unit_no 列', changed and 'unit_no' in cols)
old_row = c2.execute('SELECT * FROM bill WHERE id=1').fetchone()
check('迁移保留原账单数据', old_row is not None and old_row['amount_receivable'] == 10000
      and old_row['unit_no'] == '')
check('重复迁移为幂等操作', db.migrate(c2) is False)
c2.close()

print('\n' + '=' * 50)
failed = [n for n, ok in checks if not ok]
print(f'测试结果：{len(checks) - len(failed)}/{len(checks)} 项通过')
if failed:
    print('失败项：')
    for n in failed:
        print('  - ' + n)
    sys.exit(1)
print('全部通过 ✓')
