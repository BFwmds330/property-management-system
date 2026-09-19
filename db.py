# -*- coding: utf-8 -*-
"""数据库初始化与连接管理（SQLite 单文件库，零外部依赖，首次运行自动建库建表）。

金额统一以"分"（INTEGER）存储，避免浮点误差；
主键统一为自增 INTEGER id；
外键全部开启（PRAGMA foreign_keys=ON），小区删除时级联清理全部下级数据。
"""
import os
import shutil
import sqlite3
from datetime import datetime

_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_ROOT, 'data')
# 允许通过环境变量替换数据库位置（供自动化测试使用）
DB_PATH = os.environ.get('PROPERTY_DB_PATH') or os.path.join(DATA_DIR, 'property.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS community (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT    NOT NULL UNIQUE,
  address         TEXT    NOT NULL DEFAULT '',
  area_land       REAL    NOT NULL DEFAULT 0,
  area_building   REAL    NOT NULL DEFAULT 0,
  green_rate      REAL    NOT NULL DEFAULT 0,
  plan_buildings  INTEGER NOT NULL DEFAULT 0,
  parking_total   INTEGER NOT NULL DEFAULT 0,
  delivery_date   TEXT    NOT NULL DEFAULT '',
  takeover_date   TEXT    NOT NULL DEFAULT '',
  service_phone   TEXT    NOT NULL DEFAULT '',
  remark          TEXT    NOT NULL DEFAULT '',
  created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS building (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  community_id    INTEGER NOT NULL REFERENCES community(id) ON DELETE CASCADE,
  code            TEXT    NOT NULL,
  unit_count      INTEGER NOT NULL DEFAULT 1,
  floors          INTEGER NOT NULL DEFAULT 1,
  has_elevator    INTEGER NOT NULL DEFAULT 0,
  delivery_status TEXT    NOT NULL DEFAULT '已交付',
  remark          TEXT    NOT NULL DEFAULT '',
  UNIQUE (community_id, code)
);

CREATE TABLE IF NOT EXISTS house_type (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  community_id    INTEGER NOT NULL REFERENCES community(id) ON DELETE CASCADE,
  name            TEXT    NOT NULL,
  rooms           INTEGER NOT NULL DEFAULT 1,
  halls           INTEGER NOT NULL DEFAULT 1,
  baths           INTEGER NOT NULL DEFAULT 1,
  area            REAL    NOT NULL DEFAULT 0,
  orientation     TEXT    NOT NULL DEFAULT '南',
  has_balcony     INTEGER NOT NULL DEFAULT 0,
  has_bay_window  INTEGER NOT NULL DEFAULT 0,
  has_garden      INTEGER NOT NULL DEFAULT 0,
  remark          TEXT    NOT NULL DEFAULT '',
  UNIQUE (community_id, name)
);

CREATE TABLE IF NOT EXISTS resident (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  name              TEXT    NOT NULL,
  gender            TEXT    NOT NULL DEFAULT '保密',
  birth_date        TEXT    NOT NULL DEFAULT '',
  id_type           TEXT    NOT NULL DEFAULT '身份证',
  id_number         TEXT    NOT NULL DEFAULT '',
  phone             TEXT    NOT NULL DEFAULT '',
  wechat            TEXT    NOT NULL DEFAULT '',
  workplace         TEXT    NOT NULL DEFAULT '',
  emergency_contact TEXT    NOT NULL DEFAULT '',
  emergency_phone   TEXT    NOT NULL DEFAULT '',
  remark            TEXT    NOT NULL DEFAULT '',
  created_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS house (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  community_id      INTEGER NOT NULL REFERENCES community(id) ON DELETE CASCADE,
  building_id       INTEGER NOT NULL REFERENCES building(id) ON DELETE CASCADE,
  unit              INTEGER NOT NULL DEFAULT 1,
  floor             INTEGER NOT NULL DEFAULT 1,
  room_no           TEXT    NOT NULL,
  area_gross        REAL    NOT NULL DEFAULT 0,
  area_inner        REAL    NOT NULL DEFAULT 0,
  house_type_id     INTEGER REFERENCES house_type(id) ON DELETE SET NULL,
  status            TEXT    NOT NULL DEFAULT '空置',
  owner_resident_id INTEGER REFERENCES resident(id) ON DELETE SET NULL,
  checkin_date      TEXT    NOT NULL DEFAULT '',
  remark            TEXT    NOT NULL DEFAULT '',
  UNIQUE (building_id, unit, floor, room_no)
);

CREATE TABLE IF NOT EXISTS resident_house (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  resident_id  INTEGER NOT NULL REFERENCES resident(id) ON DELETE CASCADE,
  house_id     INTEGER NOT NULL REFERENCES house(id) ON DELETE CASCADE,
  rel_type     TEXT    NOT NULL,            -- 业主 / 家庭成员 / 租户
  relation     TEXT    NOT NULL DEFAULT '', -- 家庭成员与业主的关系
  is_current   INTEGER NOT NULL DEFAULT 1,  -- 1 在住 / 0 历史
  start_date   TEXT    NOT NULL DEFAULT '',
  end_date     TEXT    NOT NULL DEFAULT '',
  is_living    INTEGER NOT NULL DEFAULT 1,  -- 是否常住
  rent_start   TEXT    NOT NULL DEFAULT '',
  rent_end     TEXT    NOT NULL DEFAULT '',
  rent_monthly REAL,
  remark       TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fee_item (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  community_id    INTEGER NOT NULL REFERENCES community(id) ON DELETE CASCADE,
  name            TEXT    NOT NULL,
  pricing_type    TEXT    NOT NULL,           -- 面积单价 / 按户固定 / 按车位
  unit_price      REAL,                       -- 元/㎡/月（面积单价）
  fixed_amount    REAL,                       -- 元/期（按户固定）或 元/位/期（按车位）
  period_type     TEXT    NOT NULL DEFAULT '月',
  enabled         INTEGER NOT NULL DEFAULT 1,
  remark          TEXT    NOT NULL DEFAULT '',
  UNIQUE (community_id, name)
);

CREATE TABLE IF NOT EXISTS bill (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  community_id      INTEGER NOT NULL REFERENCES community(id) ON DELETE CASCADE,
  house_id          INTEGER NOT NULL REFERENCES house(id) ON DELETE CASCADE,
  fee_item_id       INTEGER NOT NULL REFERENCES fee_item(id) ON DELETE CASCADE,
  period            TEXT    NOT NULL,
  original_amount   INTEGER NOT NULL,         -- 生成时金额（分）
  adjust_amount     INTEGER NOT NULL DEFAULT 0,
  amount_receivable INTEGER NOT NULL,         -- 当前应收（分，调整后）
  amount_received   INTEGER NOT NULL DEFAULT 0,
  status            TEXT    NOT NULL DEFAULT '未缴',
  adjust_reason     TEXT    NOT NULL DEFAULT '',
  unit_no           TEXT    NOT NULL DEFAULT '',  -- 分缴单元标识：''=整户账单；车位费=车位号/车牌
  created_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (house_id, fee_item_id, period, unit_no)
);

CREATE TABLE IF NOT EXISTS payment (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  bill_id     INTEGER NOT NULL REFERENCES bill(id) ON DELETE CASCADE,
  community_id INTEGER NOT NULL,
  amount      INTEGER NOT NULL,
  pay_date    TEXT    NOT NULL,
  method      TEXT    NOT NULL DEFAULT '现金',
  receipt_no  TEXT    NOT NULL DEFAULT '',
  operator    TEXT    NOT NULL DEFAULT '',
  remark      TEXT    NOT NULL DEFAULT '',
  created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS operation_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  community_id INTEGER,
  action       TEXT NOT NULL,
  detail       TEXT NOT NULL DEFAULT '',
  operator     TEXT NOT NULL DEFAULT '系统',
  created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS vehicle (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  house_id INTEGER NOT NULL REFERENCES house(id) ON DELETE CASCADE,
  plate    TEXT    NOT NULL,
  slot_no  TEXT    NOT NULL DEFAULT '',
  remark   TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS announcement (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  community_id INTEGER NOT NULL REFERENCES community(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  content      TEXT NOT NULL DEFAULT '',
  publish_date TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS repair (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  community_id INTEGER NOT NULL REFERENCES community(id) ON DELETE CASCADE,
  house_id     INTEGER REFERENCES house(id) ON DELETE SET NULL,
  content      TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT '待处理',
  handler      TEXT NOT NULL DEFAULT '',
  result       TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  finished_at  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_house_comm  ON house(community_id);
CREATE INDEX IF NOT EXISTS idx_bill_comm   ON bill(community_id, period);
CREATE INDEX IF NOT EXISTS idx_bill_house  ON bill(house_id);
CREATE INDEX IF NOT EXISTS idx_rh_house    ON resident_house(house_id);
CREATE INDEX IF NOT EXISTS idx_pay_bill    ON payment(bill_id);
CREATE INDEX IF NOT EXISTS idx_pay_comm    ON payment(community_id);
"""


def _table_columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({table})')]


def migrate(conn):
    """旧库结构升级：bill 表增加 unit_no 列（支持车位费按车位分缴）。

    SQLite 无法修改约束，需按官方方案重建表（先关外键，复制数据后替换）。
    返回是否执行了升级。
    """
    if 'unit_no' in _table_columns(conn, 'bill'):
        return False
    conn.executescript('''
        PRAGMA foreign_keys=OFF;
        BEGIN;
        CREATE TABLE bill_new (
          id                INTEGER PRIMARY KEY AUTOINCREMENT,
          community_id      INTEGER NOT NULL REFERENCES community(id) ON DELETE CASCADE,
          house_id          INTEGER NOT NULL REFERENCES house(id) ON DELETE CASCADE,
          fee_item_id       INTEGER NOT NULL REFERENCES fee_item(id) ON DELETE CASCADE,
          period            TEXT    NOT NULL,
          original_amount   INTEGER NOT NULL,
          adjust_amount     INTEGER NOT NULL DEFAULT 0,
          amount_receivable INTEGER NOT NULL,
          amount_received   INTEGER NOT NULL DEFAULT 0,
          status            TEXT    NOT NULL DEFAULT '未缴',
          adjust_reason     TEXT    NOT NULL DEFAULT '',
          unit_no           TEXT    NOT NULL DEFAULT '',
          created_at        TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
          UNIQUE (house_id, fee_item_id, period, unit_no)
        );
        INSERT INTO bill_new(id, community_id, house_id, fee_item_id, period, original_amount,
                             adjust_amount, amount_receivable, amount_received, status,
                             adjust_reason, created_at, unit_no)
        SELECT id, community_id, house_id, fee_item_id, period, original_amount,
               adjust_amount, amount_receivable, amount_received, status,
               adjust_reason, created_at, ''
        FROM bill;
        DROP TABLE bill;
        ALTER TABLE bill_new RENAME TO bill;
        CREATE INDEX IF NOT EXISTS idx_bill_comm ON bill(community_id, period);
        CREATE INDEX IF NOT EXISTS idx_bill_house ON bill(house_id);
        COMMIT;
        PRAGMA foreign_keys=ON;
    ''')
    return True


def connect():
    """打开（必要时创建）数据库连接并确保表结构就绪。"""
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(SCHEMA)
    if migrate(conn):
        print('[数据库升级] 已自动升级账单表：支持车位费按车位分缴，历史数据已保留。')
    conn.commit()
    return conn


def backup_db():
    """备份数据库文件到 data/backups/，返回备份文件路径。"""
    bak_dir = os.path.join(DATA_DIR, 'backups')
    os.makedirs(bak_dir, exist_ok=True)
    target = os.path.join(bak_dir, f'property_{datetime.now():%Y%m%d_%H%M%S}.bak.db')
    shutil.copy2(DB_PATH, target)
    return target


def list_backups():
    """列出全部备份：[(文件名, 大小字节, 修改时间), ...] 按时间升序。"""
    bak_dir = os.path.join(DATA_DIR, 'backups')
    if not os.path.isdir(bak_dir):
        return []
    out = []
    for fn in sorted(os.listdir(bak_dir)):
        if fn.endswith('.db'):
            p = os.path.join(bak_dir, fn)
            out.append((fn, os.path.getsize(p),
                        datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M:%S')))
    return out


def restore_db(path):
    """用指定备份覆盖当前数据库（调用方需先关闭现有连接）。"""
    shutil.copy2(path, DB_PATH)
