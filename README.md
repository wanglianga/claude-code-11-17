# 实验室原料检验数据治理服务

接收实验室原始记录（CSV / JSON），关联取样与供货批次，统一计量含义，按随附业务规则
生成**可复核的项目判定与整批结论**。针对题目中的两类真实事故设计：

1. **单位口径不一致**：同一项目一份 `mg/kg`、一份 `ug/kg`，汇总表只比数字导致高风险批次
   被误判合格 —— 本服务换算前先核对量纲与适用基质，全部归一到基准单位后再判定。
2. **低于检出限被填成零**：本服务把**数值、上下界、定性描述分开保存**，未检出存为
   区间 `[0, 检出限]` 而不是精确值 0；判定按区间比较，横跨限值即交人工复核。

> 判定限值全部来自随附 `data/reference/decision_rules.json`（演示用虚构规则），
> 系统不自行套用任何真实行业限值。

## 一、技术栈与存储分层

- Python 3.12 + FastAPI + SQLAlchemy 2 + PostgreSQL（纯后端，提供 OpenAPI 3.1 / Swagger UI）
- 三层存储，职责分离：

| 层 | 表 | 说明 |
| --- | --- | --- |
| 采集原件 | `import_files`、`raw_records` | 文件与行级原文、内容指纹、坏行原因，永不丢弃 |
| 标准化结果 | `units`、`decision_rules`、`samples`、`result_groups`、`standardized_results`、`conflicts` | 版本化结果，数值/区间/定性三分，冲突并列 |
| 批准记录 | `batch_conclusions`、`reports`、`audit_events` | 批次结论、报告版本与撤回历史链、操作留痕 |

## 二、目录结构

```
app/                后端源码（models/units/parser/processing/judgment/batch/reports/routers）
data/reference/     随附参考数据：单位表、样品档案、判定规则、异常记录
data/raw/           随附原始记录：LAB-A CSV、LAB-B JSON、同号修订 CSV
scripts/            容器入口与一键演示脚本
tests/              40 个 pytest 用例（纯逻辑 + 全链路 + HTTP 接口）
Dockerfile / docker-compose.yml  一键启动
```

## 三、本地启动

### 方式 A：Docker Compose（一键，自带 PostgreSQL）

```bash
docker compose up --build
# 服务：http://localhost:8000  ；Swagger UI：http://localhost:8000/docs
```

容器入口会自动等待数据库、建表、幂等装载 `data/reference` 参考数据后启动 API。

### 方式 B：本地 Python（使用容器内/本机已运行的 PostgreSQL）

```bash
# 1. 建虚拟环境并装依赖
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 准备数据库（库/用户/密码 ccdev，与本机 PostgreSQL 一致）
createdb -h 127.0.0.1 -U ccdev qc_lab   # 如已存在可跳过

# 3. 建表 + 装载随附参考数据（单位/样品/规则/异常记录，幂等可重复执行）
.venv/bin/python -m app.cli init-db
.venv/bin/python -m app.cli seed

# 4. 启动服务
.venv/bin/python -m app.cli run --port 8000
```

配置通过环境变量或 `.env`（见 `.env.example`）覆盖，默认
`DATABASE_URL=postgresql+psycopg2://ccdev:ccdev@127.0.0.1:5432/qc_lab`。

## 四、测试账号（仅隔离开发环境）

角色通过 `Authorization: Bearer <token>` 或 `X-API-Token` 传递：

| 角色 | 令牌 | 权限 |
| --- | --- | --- |
| inspector 检验员 | `token-inspector-001` | 导入记录、提交报告、查询 |
| reviewer 复核员 | `token-reviewer-001` | 冲突处理、样品失效、批准/撤回、查询 |
| admin 管理员 | `token-admin-001` | 参考数据种子、全量查询 |

## 五、验证方式

### 自动化测试（推荐，无需起服务）

```bash
# 测试库 qc_lab_test 需可连接（PostgreSQL 本机 ccdev 账号）
createdb -h 127.0.0.1 -U ccdev qc_lab_test   # 如已存在可跳过
.venv/bin/python -m pytest
```

覆盖：量纲/基质核对、稀释只修正一次、区间判定三种走向、行级坏行容错、
指纹去重、同号修订版本链、异源冲突并列、缺质量挂起总量、失效样品隔离、
批次前置条件、批准前重读漂移打回、撤回历史链等。

### 一键 HTTP 演示（服务已启动时）

```bash
bash scripts/demo.sh
```

### 手工关键接口（Swagger UI 可直接试）

```bash
# 导入原始记录（multipart：file + source_ref）
curl -X POST http://127.0.0.1:8000/api/import/records \
  -H "Authorization: Bearer token-inspector-001" \
  -F "source_ref=LAB-A" -F "file=@data/raw/lab_a_20261105.csv"

# 待处理视图：坏行 + 待补/挂起项（哪些项目还不能确定）
curl "http://127.0.0.1:8000/api/query/pending?batch_no=B20261101" \
  -H "Authorization: Bearer token-inspector-001"

# 生成批次结论 → 提交报告 → 复核批准 → 撤回
curl -X POST http://127.0.0.1:8000/api/reports/batch-conclusions \
  -H "Authorization: Bearer token-inspector-001" -H "Content-Type: application/json" \
  -d '{"batch_no":"B20261102"}'
```

## 六、随附数据与场景对照

| 题面要求 | 随附数据 / 系统行为 |
| --- | --- |
| mg/kg 与 ug/kg 口径陷阱 | `RA-001` 报 `18 ug/kg`（稀释10）归一为 `0.18 mg/kg`；`RB-001` 报 `0.35 mg/kg`，两者冲突并列 |
| 低于检出限不能填零 | `RA-003` ND + 检出限 2 ug/kg → 区间 `[0, 0.002] mg/kg`，`numeric_value` 为空 |
| 坏行进待处理不漏掉 | `RA-006` 缺单位、`RA-013` 读数 `NA`：文件整体入库，2 行带原因 `pending` |
| 未检出却无检出限 | `RA-007` → `pending_value`，不能确定上界 |
| 缺质量/体积停待补 | S-003 无质量、S-102 无体积：浓度仍判定，`total_pending=true`，不擅自换算总量 |
| 量纲/基质不符拒绝 | `RB-002` 用液体单位 `mg/L` 报固体样品 → `pending_unit` |
| 稀释只修正一次 | 读数与检出限同步 × 倍数，`dilution_applied` 与换算链全程留痕可回查 |
| 冲突先列不覆盖 | LAB-A/LAB-B 铅结果不一致 → `conflicts` 开放，生效版本置空 |
| 同号变值保留修订 | `lab_a_20261105_revision.csv` 的 `RA-001` → 新版本，旧版 `superseded` |
| 失效样品隔离 | S-004 由异常记录标记失效，新结果仍存原件但批次结论列为硬阻断 |
| 区间横跨限值交复核 | `RA-004` 汞 `<0.06` 对限值 0.05 → 判定 `review`，不猜合格 |
| 批准前重读版本 | 复核与修订同时到达 → 批准返回 409 版本漂移，打回重提 |
| 撤回留痕不改原文 | 已签发报告 `withdrawn` 并以 `superseded_by_id` 关联新报告，历史保留 |
| 单项通过≠整批可用 | 批次结论需归属明确、必检齐备、冲突清零、待补清零，否则 `hold` |

## 七、实际验证结论（本次开发中真实执行）

- `pytest`：**40 passed**（tests/ 下 4 个测试文件，PostgreSQL 测试库真实建表执行）。
- 本机 uvicorn 实跑 HTTP 全链路：导入/重传去重/冲突复核/批次结论/报告批准/
  修订后 409 漂移打回/撤回历史链，均返回预期；`/docs` 返回 200，`/openapi.json` 为 OpenAPI 3.1、18 个路径。
- 典型判定核对：采信 LAB-B 后 S-001 铅 `0.35 mg/kg` 对限值 `0.2` 判 `nonconform`；
  S-002 铅 `0.25` 判 `nonconform`；液体批次 B20261102 前置条件满足判 `pass`；
  固体批次 B20261101 因失效样品与待补项判 `hold` 并逐条列明阻断原因。
- Docker 交付物（Dockerfile / docker-compose.yml / entrypoint）已随工程提供；
  当前隔离容器内无 docker 守护进程，未在本机执行 `docker compose up`，镜像构建需在具备 Docker 的环境验证。
