# -*- coding: utf-8 -*-
"""数据字典与业务常量（建表 DDL 见 db.py，字段级设计说明见 docs/DESIGN.md）。"""

APP_NAME = '智慧物业管理系统'
VERSION = '1.0.0'

GENDERS = ['男', '女', '保密']
ID_TYPES = ['身份证', '护照', '其他']
REL_TYPES = ['业主', '家庭成员', '租户']
MEMBER_RELATIONS = ['配偶', '子女', '父母', '兄弟姐妹', '其他亲属', '其他']
HOUSE_STATUSES = ['空置', '自住', '出租', '装修中']
BUILDING_STATUS = ['在建', '未交付', '已交付']
PRICING_TYPES = ['面积单价', '按户固定', '按车位']
PERIOD_TYPES = ['月', '季', '年']
PAY_METHODS = ['现金', '银行转账', '扫码']
BILL_STATUSES = ['未缴', '部分缴纳', '已缴清']
REPAIR_STATUSES = ['待处理', '处理中', '已完成']

# 滞纳金日费率：日万分之五（用于欠费清单中的预估滞纳金）
LATE_FEE_DAILY_RATE = 0.0005
# 租约到期提醒阈值（天）
LEASE_REMIND_DAYS = 30
# 欠费清单醒目提醒阈值（天）
ARREARS_URGENT_DAYS = 90
