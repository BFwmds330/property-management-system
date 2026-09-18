# -*- coding: utf-8 -*-
"""演示数据生成（随机种子固定，可重复生成；支持重置覆盖全部业务数据）。

场景：2 个小区，每小区 3 栋楼、42 套房屋、40+ 位住户，
物业费/公摊水电费/车位费 2026-07 至 2026-09 三个账期的账单与缴费流水，
并包含部分缴费、欠费、30 天内到期租约等演示情景。
"""
import random
from datetime import date, timedelta

from services import (building_service, community_service, extra_service,
                      fee_service, house_service, housetype_service,
                      log_service, resident_service)

SURNAMES = ('王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭肖田董潘袁蔡蒋余杜'
            '叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛段雷侯龙陶黎贺')
GIVEN = ['伟', '芳', '娜', '敏', '静', '丽', '强', '磊', '军', '洋', '勇', '艳', '杰', '娟', '涛',
         '明', '超', '霞', '平', '刚', '秀英', '文博', '思远', '雨欣', '子涵', '浩然', '欣怡',
         '梓萱', '宇轩', '俊杰', '晓彤', '嘉懿', '慧敏', '志强', '建国', '淑兰', '国庆', '建军',
         '小红', '志明', '丽华', '海燕', '春花', '德福', '秀兰', '桂芳', '文静', '天佑', '若曦']
WORKPLACES = ['国贸中心', '市人民医院', '实验小学', '城建集团', '移动公司', '自由职业', '个体经营', '机关单位']
OPERATORS = ['张会计', '李出纳', '王前台']
EMERGENCY = ['李女士', '王先生', '刘先生', '陈女士', '赵先生', '孙女士']

_COMMUNITIES = [
    dict(name='阳光花园', address='北京市朝阳区阳光路 1 号', area_land=52000.0, area_building=118000.0,
         green_rate=35.5, plan_buildings=3, parking_total=120, delivery_date='2019-06-30',
         takeover_date='2019-07-01', service_phone='010-88886666', remark='市级示范住宅小区'),
    dict(name='翠湖天地', address='杭州市西湖区翠湖路 88 号', area_land=38000.0, area_building=96000.0,
         green_rate=40.2, plan_buildings=3, parking_total=96, delivery_date='2021-09-30',
         takeover_date='2021-10-08', service_phone='0571-66668888', remark='湖景高层社区'),
]

# 楼栋配置：(编号, 单元数, 层数, 有电梯)
_BUILDINGS = [('1#', 2, 6, 1), ('2#', 1, 6, 1), ('3#', 1, 6, 1)]

_HOUSE_TYPES = [
    ('一室一厅一卫', 1, 1, 1, 52.0, '南', 1, 0, 0, ''),
    ('两室两厅一卫', 2, 2, 1, 78.0, '南北通透', 1, 1, 0, ''),
    ('三室两厅两卫 A 户型', 3, 2, 2, 118.0, '南北通透', 1, 1, 0, '边户采光好'),
    ('四室两厅三卫', 4, 2, 3, 156.0, '南', 1, 0, 1, '带入户花园'),
]


def _names(rng, n, used):
    """从姓池+名池中取 n 个不重复的中文姓名。"""
    out = []
    while len(out) < n:
        nm = rng.choice(SURNAMES) + rng.choice(GIVEN)
        if nm not in used:
            used.add(nm)
            out.append(nm)
    return out


def _fake_idcard(rng, birth, gender):
    """生成通过 GB 11643 校验位算法的演示身份证号。"""
    area = rng.choice(['110105', '310104', '440304', '330106', '510107'])
    seq = rng.randint(0, 499) * 2 + (1 if gender == '男' else 0)
    body = f'{area}{birth.replace("-", "")}{seq:03d}'
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check = '10X98765432'
    s = sum(int(c) * w for c, w in zip(body, weights))
    return body + check[s % 11]


def load_demo(conn, reset=False):
    """生成并载入演示数据，返回结果说明文本。reset=True 时先清空全部业务数据。"""
    rng = random.Random(2026)
    if reset:
        for table in ('payment', 'bill', 'resident_house', 'vehicle', 'announcement', 'repair',
                      'operation_log', 'house', 'fee_item', 'house_type', 'building',
                      'resident', 'community'):
            conn.execute(f'DELETE FROM {table}')
        conn.commit()

    used_names = set()
    receipt_seq = 0
    person_total = house_total = bill_total = pay_total = 0

    for comm in _COMMUNITIES:
        cid = community_service.create(conn, comm)
        for code, units, floors, lift in _BUILDINGS:
            building_service.create(conn, cid, dict(
                code=code, unit_count=units, floors=floors, has_elevator=lift,
                delivery_status='已交付', remark=''))
        type_ids = {}
        for name, r, h, b, area, ori, bal, bay, gar, rk in _HOUSE_TYPES:
            type_ids[name] = housetype_service.create(conn, cid, dict(
                name=name, rooms=r, halls=h, baths=b, area=area, orientation=ori,
                has_balcony=bal, has_bay_window=bay, has_garden=gar, remark=rk))

        # 批量生成房屋：1# 两个单元（三室/两室），2# 一室，3# 四室，共 42 套
        buildings = {b['code']: b for b in building_service.list_with_count(conn, cid)}
        house_service.batch_generate(conn, cid, buildings['1#'], 1, 1, 6, 2,
                                     type_ids['三室两厅两卫 A 户型'])
        house_service.batch_generate(conn, cid, buildings['1#'], 2, 1, 6, 2,
                                     type_ids['两室两厅一卫'])
        house_service.batch_generate(conn, cid, buildings['2#'], 1, 1, 6, 2,
                                     type_ids['一室一厅一卫'])
        house_service.batch_generate(conn, cid, buildings['3#'], 1, 1, 6, 1,
                                     type_ids['四室两厅三卫'])
        houses = house_service.search(conn, cid, kw='', limit=1000)
        house_total += len(houses)

        # 住户：约 85% 房屋有业主，其余空置
        owned_idx = set(rng.sample(range(len(houses)), int(len(houses) * 0.85)))
        owner_names = _names(rng, len(owned_idx), used_names)
        phone_set = set()

        def rand_phone():
            while True:
                p = '1' + rng.choice('3589') + ''.join(rng.choices('0123456789', k=8))
                if p not in phone_set:
                    phone_set.add(p)
                    return p

        def make_person(name):
            gender = rng.choice(['男', '女'])
            birth = f'{rng.randint(1955, 2005):04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}'
            phone = rand_phone()
            return dict(
                name=name, gender=gender, birth_date=birth, id_type='身份证',
                id_number=_fake_idcard(rng, birth, gender), phone=phone,
                wechat='wx_' + phone[-8:], workplace=rng.choice(WORKPLACES),
                emergency_contact=rng.choice(EMERGENCY), emergency_phone=rand_phone(), remark='')

        person_total += len(owned_idx)
        for i, idx in enumerate(sorted(owned_idx)):
            h = houses[idx]
            rid = resident_service.add_person(conn, make_person(owner_names[i]))
            resident_service.link(conn, h['id'], rid, '业主',
                                  start_date=f'{rng.randint(2020, 2024)}-{rng.randint(1, 12):02d}-'
                                             f'{rng.randint(1, 28):02d}')

        # 租户：挑 6 套已售房屋出租，租约到期日覆盖 15/45/120 天后等情景
        rented = rng.sample(sorted(owned_idx), 6)
        end_days = [15, 45, 120, 200, 260, 300]
        for j, idx in enumerate(rented):
            h = houses[idx]
            house_service.set_status(conn, h['id'], '出租')
            rid = resident_service.add_person(conn, make_person(_names(rng, 1, used_names)[0]))
            resident_service.link(conn, h['id'], rid, '租户',
                                  rent_start=(date.today() - timedelta(days=165)).isoformat(),
                                  rent_end=(date.today() + timedelta(days=end_days[j])).isoformat(),
                                  rent_monthly=float(rng.randrange(2000, 8200, 100)))
            person_total += 1

        # 家庭成员：8 户各 1 名
        for idx in rng.sample(sorted(owned_idx - set(rented)), 8):
            h = houses[idx]
            rid = resident_service.add_person(conn, make_person(_names(rng, 1, used_names)[0]))
            resident_service.link(conn, h['id'], rid, '家庭成员',
                                  relation=rng.choice(['配偶', '子女', '父母']),
                                  is_living=rng.choice([1, 1, 0]))
            person_total += 1

        # 车辆：10 户登记车牌，用于车位费演示
        for idx in rng.sample(sorted(owned_idx), 10):
            h = houses[idx]
            plate = rng.choice(['京A', '京B', '京C', '京D']) + \
                ''.join(rng.choices('ABCDEFGHJKLMNPQRSTUVWXYZ123456789', k=5))
            extra_service.add_vehicle(conn, h['id'], plate, slot_no=f'D{rng.randint(1, 120):03d}')

        # 收费项目
        fee_service.create_item(conn, cid, dict(
            name='物业费', pricing_type='面积单价', unit_price=2.30, period_type='月',
            enabled=True, remark='按建筑面积计收'))
        fee_service.create_item(conn, cid, dict(
            name='公摊水电费', pricing_type='按户固定', fixed_amount=20.0, period_type='月',
            enabled=True, remark=''))
        fee_service.create_item(conn, cid, dict(
            name='车位费', pricing_type='按车位', fixed_amount=150.0, period_type='月',
            enabled=True, remark='产权车位使用费'))

        # 生成 2026-07/08/09 三个账期的账单，并按情景缴费（含部分缴费与欠费）
        for period in ('2026-07', '2026-08', '2026-09'):
            for it in fee_service.items(conn, cid):
                fee_service.generate(conn, cid, it, period)
            bills = conn.execute(
                'SELECT b.* FROM bill b WHERE b.community_id=? AND b.period=?',
                (cid, period)).fetchall()
            bill_total += len(bills)
            for b in bills:
                balance = b['amount_receivable'] - b['amount_received']
                r = rng.random()
                if period == '2026-07':
                    plan = 'full' if r < 0.90 else ('part' if r < 0.95 else 'none')
                elif period == '2026-08':
                    plan = 'full' if r < 0.80 else ('part' if r < 0.88 else 'none')
                else:
                    plan = 'full' if r < 0.35 else ('part' if r < 0.45 else 'none')
                if plan == 'none':
                    continue
                amount = balance if plan == 'full' else int(balance * rng.uniform(0.3, 0.7))
                day = rng.randint(1, 28) if period != '2026-09' else rng.randint(1, 18)
                receipt_seq += 1
                fee_service.pay(conn, b['id'], amount, f'{period}-{day:02d}',
                                rng.choice(['现金', '银行转账', '扫码']),
                                f'SK{receipt_seq:06d}', rng.choice(OPERATORS))
                pay_total += 1

        # 公告与报修
        extra_service.add_announcement(conn, cid, '关于台风天气的温馨提示',
                                       '台风期间请关闭门窗，收好阳台悬挂物，减少不必要外出。',
                                       '2026-09-05')
        extra_service.add_announcement(conn, cid, '小区停水通知',
                                       '因市政管网改造，本周六 9:00-17:00 全区停水，请提前储水。',
                                       '2026-09-10')
        extra_service.add_announcement(conn, cid, '国庆节物业值班安排',
                                       '国庆假期物业服务中心照常值班，24 小时服务电话不变。',
                                       '2026-09-12')
        rep_ids = [
            extra_service.add_repair(conn, cid, houses[3]['id'], '厨房下水道堵塞，返水严重'),
            extra_service.add_repair(conn, cid, houses[7]['id'], '入户门锁损坏，无法正常上锁'),
            extra_service.add_repair(conn, cid, houses[11]['id'], '客厅窗户漏风，需更换密封条'),
            extra_service.add_repair(conn, cid, None, '3 号楼单元门禁失灵（公共区域）'),
        ]
        extra_service.update_repair(conn, rep_ids[0], '已完成', '维修部-老周', '已疏通并更换止逆阀')
        extra_service.update_repair(conn, rep_ids[1], '处理中', '维修部-小李', '')

    log_service.add(conn, None, '载入演示数据',
                    f'已生成 {len(_COMMUNITIES)} 个小区、{house_total} 套房屋、'
                    f'{person_total} 位住户、{bill_total} 笔账单、{pay_total} 笔缴费记录')
    return (f'演示数据载入完成：{len(_COMMUNITIES)} 个小区 / {house_total} 套房屋 / '
            f'{person_total} 位住户 / {bill_total} 笔账单 / {pay_total} 笔缴费记录')
