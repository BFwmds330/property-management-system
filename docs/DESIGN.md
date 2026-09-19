# 设计说明（数据模型 · 菜单结构树 · 关键规则）

## 一、技术选型说明

| 项 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.10+ | 标准库能力足够（sqlite3/csv/decimal），开发效率高，适合单机终端工具 |
| 存储 | SQLite 单文件（`sqlite3` 标准库） | 免安装数据库服务、单机可用、事务与外键级联完整支持 |
| 界面 | 纯标准库实现菜单 + 自研表格渲染 | 不引入 tabulate/rich 等第三方依赖，中文全角字符按宽度 2 对齐 |
| 金额 | 整数"分"（INTEGER）+ `decimal.Decimal` 解析输入 | 避免浮点误差，报表与手工核算完全一致 |
| 架构 | 三层：`ui/`（交互）→ `services/`（业务）→ `db.py`（存储） | 业务逻辑与终端解耦，可直接写自动化测试（tests/smoke_test.py 即服务层端到端测试） |

## 二、数据模型

### 表结构一览

| 表 | 说明 | 关键字段 |
|---|---|---|
| `community` | 小区 | name（**唯一**）、address、area_land、area_building、green_rate、plan_buildings、parking_total、delivery_date、takeover_date、service_phone、remark |
| `building` | 楼栋 | community_id（FK→community，级联）、code（**唯一**：community_id+code）、unit_count、floors、has_elevator、delivery_status |
| `house_type` | 户型（小区级库） | community_id（FK，级联）、name（**唯一**：community_id+name）、rooms/halls/baths、area、orientation、has_balcony/has_bay_window/has_garden |
| `house` | 房屋 | building_id（FK→building，级联）、unit/floor/room_no（**唯一**：building_id+unit+floor+room_no）、area_gross/area_inner、house_type_id（FK→house_type，**SET NULL**）、status（空置/自住/出租/装修中）、owner_resident_id（FK→resident，SET NULL，冗余当前业主便于查询） |
| `resident` | 住户人员档案 | name、gender、birth_date、id_type、id_number（18 位身份证校验位校验）、phone（11 位校验）、wechat、workplace、emergency_contact/phone |
| `resident_house` | 住户-房屋关系（支撑历史轨迹） | resident_id（FK，级联）、house_id（FK，级联）、rel_type（业主/家庭成员/租户）、relation（与业主关系）、**is_current（1 在住 / 0 历史）**、start_date/end_date、is_living、rent_start/rent_end/rent_monthly（租户专用） |
| `fee_item` | 收费项目 | community_id（FK，级联）、name（**唯一**：community_id+name）、pricing_type（面积单价/按户固定/按车位）、unit_price（元/㎡/月）、fixed_amount（元/期 或 元/位/期）、period_type（月/季/年）、enabled |
| `bill` | 账单 | house_id（FK，级联）、fee_item_id（FK，级联）、period（账期）、original_amount、adjust_amount、adjust_reason、amount_receivable、amount_received、status（未缴/部分缴纳/已缴清）、**unit_no（分缴单元标识：''=整户账单，车位费=车位号/车牌）**，**唯一**：house_id+fee_item_id+period+unit_no |
| `payment` | 缴费流水 | bill_id（FK，级联）、amount、pay_date、method（现金/银行转账/扫码）、receipt_no、operator |
| `operation_log` | 关键操作日志 | community_id、action、detail、operator、created_at |
| `vehicle` | 车辆（可选扩展） | house_id（FK，级联）、plate、slot_no |
| `announcement` | 公告（可选扩展） | community_id（FK，级联）、title、content、publish_date |
| `repair` | 报修（可选扩展） | community_id（FK，级联）、house_id（FK，SET NULL，可公共区域）、content、status（待处理/处理中/已完成）、handler、result、finished_at |

### 关键约束与策略

1. **唯一键**：小区名；小区内楼栋编号；小区内户型名；楼栋+单元+楼层+房号；房屋+收费项目+账期（防重复生成账单）。
2. **外键与级联**：`PRAGMA foreign_keys=ON`。删除小区 → 级联删除楼栋 → 房屋 → 住户关系/账单 → 缴费流水（删除前二次确认并提示影响范围，写操作日志）；删除房屋同理。删除户型：被房屋引用时**禁止删除**（避免房屋悬空）；删除收费项目：被账单引用时禁止删除，只能停用。
3. **金额精度**：账单应收/已收、缴费金额一律为整数分；输入端用 `decimal.Decimal` 校验两位小数后 ×100 转分；展示端用整数运算格式化，全程无浮点参与。
4. **软删除 vs 硬删除**：业务数据采用**硬删除 + 级联**（删除前二次确认 + 操作日志留痕）；而"住户变动"不删数据——通过 `resident_house.is_current/end_date` 实现**历史留痕**（搬出、退租、过户均只关闭当前关系并新增/清空，历史轨迹可完整回溯）。账单删除仅允许"未缴且无任何缴费记录"的账单，并写操作日志。
5. **主键风格**：全部自增 INTEGER id，风格统一。
6. **数据安全**：`data/property.db` 单文件，程序内一键备份到 `data/backups/`、恢复需二次确认；未预期异常全局兜底并记录 `data/error.log`，程序不崩溃退出。
7. **结构升级**：v1.1 账单表增加 `unit_no` 列（车位费按车位分缴）。程序启动时自动检测旧库结构并按 SQLite 官方方案重建表迁移（关外键 → 建新表 → 复制数据 → 换名 → 重建索引），历史数据全部保留，迁移幂等。

## 三、菜单结构树

```text
主菜单（页头显示当前小区）
├── 1 小区管理
│   ├── 1 新增小区                ├── 4 查询小区（名称/地址模糊）
│   ├── 2 修改小区信息            ├── 5 小区汇总列表（楼栋/房屋/住户/欠费）
│   ├── 3 删除小区（二次确认）     └── 6 切换当前小区
├── 2 房屋与户型管理
│   ├── 1 楼栋管理：1 新增 / 2 修改 / 3 删除（级联确认）/ 4 列表
│   ├── 2 房屋管理
│   │   ├── 1 登记房屋              ├── 5 房屋状态变更
│   │   ├── 2 批量生成房屋          ├── 6 产权过户（留痕）
│   │   ├── 3 房屋列表与筛选+详情    └── 7 删除房屋（级联确认）
│   │   └── 4 修改房屋信息
│   └── 3 户型管理：1 新增 / 2 修改（引用影响提示）/ 3 删除 / 4 列表 / 5 分布统计
├── 3 住户信息管理
│   ├── 1 业主入住登记            ├── 7 房屋住户历史轨迹
│   ├── 2 添加家庭成员            ├── 8 住户搜索（姓名/手机号/房号）
│   ├── 3 登记租户（到期提醒）     ├── 9 导出住户通讯录 CSV
│   ├── 4 房屋住户列表            ├── 10 租约到期提醒（30 天）
│   ├── 5 修改住户资料            └── 11 车辆信息登记
│   └── 6 住户搬出/退租
├── 4 物业收费管理
│   ├── 1 收费项目配置：1 新增 / 2 修改 / 3 删除 / 4 列表
│   ├── 2 生成账单（预览应收总额）
│   ├── 3 账单查询（房号/项目/账期/状态，可导出；可删除未缴账单）
│   ├── 4 登记缴费（部分缴费；a=一房多单一次缴清）
│   ├── 5 欠费清单（欠费天数/预估滞纳金/超 90 天标红）
│   ├── 6 导出催缴单 CSV
│   ├── 7 模拟催缴短信（可保存文本）
│   ├── 8 缴费记录查询（多条件，可导出）
│   └── 9 账单金额调整（减免必填原因，日志留痕）
├── 5 统计报表
│   ├── 1 账期收缴报表            ├── 3 欠费金额 Top 10
│   ├── 2 年度收缴报表            ├── 4 各小区收缴率对比
│   │                             └── 5 每户车辆统计（车位分缴情况）
├── 6 公告与报修
│   ├── 1 小区公告管理：1 发布 / 2 列表查看 / 3 修改 / 4 删除
│   └── 2 报修管理：1 登记 / 2 列表 / 3 状态流转
├── 7 系统工具
│   ├── 1 备份数据库              ├── 4 重置并重载演示数据（双重确认）
│   ├── 2 恢复数据库（二次确认）   └── 5 关于本系统
│   └── 3 查看操作日志
└── 0 退出系统
```

## 四、关键业务规则

1. **账单生成**：金额 = 单价 × 建筑面积 × 月数（月/季/年 = 1/3/12）；按户固定 = 固定金额/期；**按车位 = 每个车位一张独立账单（分缴），金额 = 固定金额/车位/期，账单以车位号（无车位号时用车牌）作为分缴标识 `unit_no`**。应收不足 0.01 元不生成。
2. **车位分缴**：每个车位的账单可独立全额/部分缴纳、独立调整、独立出现在欠费清单与车辆统计中；同一房屋+项目+账期+车位唯一，重复生成自动跳过；若该账期存在旧版"整户"车位费账单（unit_no=''），阻止重新生成并提示先删除未缴旧账单，避免重复计费。
2. **账单状态流转**：`未缴 →（实收>0）→ 部分缴纳 →（实收≥应收）→ 已缴清`；调整应收金额后状态自动重算；已缴清账单拒绝继续缴费。
3. **欠费天数**：自计费周期期末日（月账=月末、季账=季末、年账=年末）起算至今天；预估滞纳金 = 欠费余额 × 0.0005 × 欠费天数。
4. **收缴率** = 实收 ÷ 应收 × 100%；账期报表按 `bill.period` 精确匹配，年度报表按账期前缀匹配（兼容三种账期格式）。
5. **产权过户留痕**：旧业主 `resident_house` 记录 `is_current=0、end_date=过户日`，新业主新增在住记录，`house.owner_resident_id` 同步更新，操作写入 `operation_log`。
6. **业务约束**：一房同时仅一名在住业主（更换须走过户）、一名在住租户（退租后方可再登记）；租户登记可将房屋状态联动为"出租"，退租可联动为"空置"。
7. **健壮性**：所有输入经统一校验（手机号 11 位、身份证 18 位含校验位、日期/账期格式、金额非负两位小数、整数范围）；输入 `q` 随时取消；危险操作二次确认；全局异常兜底写 `data/error.log`。

## 五、验收标准对照

| 验收项 | 实现与验证 |
|---|---|
| ≥2 小区、自由切换、数据隔离 | 所有业务查询均按 community_id 过滤；tests/smoke_test.py 第 1 组断言 |
| 批量生成楼栋房屋并绑定户型 | `house_service.batch_generate`；冒烟测试第 2 组 |
| 一房 1 业主 + 2 成员 + 1 租户并可查 | 冒烟测试第 3 组（房屋当前住户=4） |
| 月账单 + 部分缴费 + 全额缴费状态流转 | 冒烟测试第 4 组 |
| 欠费金额/收缴率与手工核算一致 | 冒烟测试第 5 组（100㎡×2 元=200 元、实收 50、收缴率 25%、欠费 150） |
| 重启数据不丢失 | 冒烟测试第 9 组（重连后数量一致） |
| 乱输入不崩溃 | 校验层 + 全局异常兜底 + 终端交互回归（tests/e2e_input.txt） |
| 报表/通讯录导出 CSV | 冒烟测试第 8 组 + 各报表界面导出入口 |
