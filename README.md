# MushroomShed-01 · 菇房出菇台账

食用菌菇房「出菇室环境记录与采收台账」种子项目（非库存 / 电商 / 医院 / 考勤）。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11 · Flask · SQLAlchemy 2 · Marshmallow · Flask-JWT-Extended · passlib(bcrypt) · gunicorn |
| 前端 | SolidJS · Vite · TypeScript · @solidjs/router |
| 数据库 | MySQL 8（协议兼容原 MariaDB 设计） |
| 部署 | docker-compose · 前端 Nginx 反代 `/api` |

## 端口与账号

| 服务 | 端口 |
| --- | --- |
| 前端 | **3800** |
| 后端 API | **8800** |
| MySQL | **3310** |

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | admin（场长） |
| `fruiter` | `123456` | fruiter（出菇员） |

数据库：`mushroomshed` / `mushroomshed`，库名 `mushroomshed`。JWT 密钥环境变量 **`JWT_SECRET`**。

## 一键启动

```bash
cd MushroomShed-01
docker compose up --build
```

启动后访问：

- 前端：http://localhost:3800
- 后端健康检查：http://localhost:8800/api/health

后端 entrypoint 流程：等待 MySQL 就绪 → `create_all` 建表 → seed 初始数据 → 启动 gunicorn。

## 功能模块

1. **Auth**：JWT 登录（OAuth2 表单或 JSON），`/api/auth/login`、`/api/auth/me`，`Authorization: Bearer`
2. **Shed 菇房**：`name`、`location`、`notes`
3. **Room 出菇室**：`shedId`、`roomCode`、`species`、`capacityBags`、`status(fruiting|idle|sanitize)`；同菇房 `roomCode` 唯一
4. **ClimateLog 环境记录**：`roomId`、`recordedAt`、`tempC`、`humidityPct`、`co2Ppm`、`notes`；`humidityPct ∈ [1,100]`，否则 **400**
5. **FlushHarvest 采收**：`roomId`、`harvestedAt`、`flushNo(≥1)`、`weightKg`、`grade(A|B|C)`、`operatorName`；`weightKg > 0`，否则 **400**
6. **Dashboard**：`shedTotal`、`fruitingRoomCount`、`climateLast24h`、`harvestKgLast7d`
7. **出菇室利用率看板**：`GET /api/utilization` 与 `GET /api/utilization-check`（同一口径 + 对账）

各实体 API：`GET/POST` 列表与创建、`DELETE` 按 ID 删除。

## 出菇室利用率口径（utilization）

主看板接口与对账接口**共用同一套筛选与公式**（`backend/app/services/utilization.py`），禁止各写一套。

- 接口
  - `GET /api/utilization?days=7&roomId=<可选>`：返回 `days`、`roomId`、`windowStart`、每室 `rooms[]`（`roomId/roomCode/species/status/capacityBags/harvestKg/climateCount/utilizationHint`）与汇总 `totalHarvestKg/totalClimateCount`。
  - `GET /api/utilization-check?days=7&roomId=<可选>`：使用**完全相同**的筛选与公式，但走「拉明细行在服务端聚合」的路径，返回 `rows`（参与统计的每笔 harvest/climate 事件）、`perRoom`（与主接口同构）与 `reconciliation`（`tolerance/maxHarvestKgDiff/maxHintDiff/passed/mismatches`）。
- 筛选口径
  - `days` 默认 **7**，须为正整数，否则 **400**；时间窗起点 `windowStart = now(UTC) - days`，含起点。
  - 采收看 `harvested_at >= windowStart`，环境记录看 `recorded_at >= windowStart`。
  - 可选 `roomId`：传入时只统计该室（两接口行为一致）。
  - 窗口内无事件的室仍返回，`harvestKg=0`、`climateCount=0`。
- 每室指标
  - `harvestKg` = 窗口内该室采收 `weightKg` 之和（kg，保留 4 位小数）。
  - `climateCount` = 窗口内该室环境记录条数。
  - `utilizationHint` 公式（唯一来源，两接口都调它）：
    - `base = harvestKg / capacityBags`
    - 状态 **`idle`**：**强制为 `0`**——即使窗口内存在历史采收，也不计利用率（采收重量本身仍计入 `harvestKg`）。
    - 状态 **`sanitize`**：在 `base` 上**再乘 `0.5`**（消杀轮作期折半）。
    - 状态 **`fruiting`**：取 `base`。
- 对账（不是只读聚合页）
  - `utilization-check` 在服务端同时跑 SQL GROUP BY 路径与明细行聚合路径，逐室比对 `harvestKg`、`utilizationHint`（绝对误差容差 **0.001**）与 `climateCount`（须完全相等），任一超限即 `reconciliation.passed=false` 并列出 `mismatches`。
  - 前端「出菇室利用率」页**先对账再展示**：同时请求两个接口，仅当服务端 `passed=true` 且前端逐室复核 `harvestKg`/`hint` 误差均 ≤ `0.001`、`climateCount` 一致时才渲染数据，否则显示对账失败与逐室差异。
  - 公斤数与 hint 一律来自后端，前端**不本地推算**任何公斤或 hint。
- 即时性：新建/删除 `FlushHarvest` 或 `ClimateLog` 成功后，前端刷新信号触发看板立即重新拉取并对账，使最新记录立刻反映到利用率。
- Seed 对照：初始数据含 `fruiting`（R-01/V-01）、`idle`（R-02，窗口内有采收但 hint 强制 0）、`sanitize`（V-02，窗口内有采收、hint 折半）三类出菇室。

## 前端页面

Login · Dashboard · Sheds · Rooms · ClimateLogs · FlushHarvests（侧边栏布局）

## 本地开发（可选）

```bash
# 数据库（或用 compose 只起 db）
docker compose up -d db

# 后端
cd backend
pip install -r requirements.txt
set DATABASE_URL=mysql+pymysql://mushroomshed:mushroomshed@localhost:3310/mushroomshed
set JWT_SECRET=local-dev-secret
python -c "from app.database import Base, engine; from app import models; Base.metadata.create_all(bind=engine)"
python -c "from app.seed import seed; seed()"
gunicorn wsgi:app --bind 0.0.0.0:8800 --reload

# 前端
cd frontend
npm install
npm run dev
```

## 目录结构

```
MushroomShed-01/
├── docker-compose.yml
├── README.md
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── requirements.txt
│   ├── wsgi.py
│   └── app/
│       ├── __init__.py
│       ├── config.py
│       ├── database.py
│       ├── auth.py
│       ├── seed.py
│       ├── utils.py
│       ├── models/
│       ├── schemas/
│       └── routes/
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── pages/
        ├── components/
        └── api/
```
