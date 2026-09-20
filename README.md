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
7. **Utilization 利用率**：`GET /api/utilization` 与对账接口 `GET /api/utilization-check`（口径见下节）

各实体 API：`GET/POST` 列表与创建、`DELETE` 按 ID 删除。

## 利用率看板与对账口径

两个接口共用**同一份实现** `backend/app/services/utilization.py`（筛选解析 + 公式），
不是两套各写；对账接口只是把同一批行数据换一种形状返回。

**筛选参数（两接口完全一致）**

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `days` | `7` | 统计窗口天数，整数 `1–90`，否则 **400** |
| `roomId` | 全部 | 可选，按出菇室过滤 |
| `asOf` | 当前时间(UTC) | 可选 ISO 8601，钉住窗口右端；前端对账时两次请求传同一个值 |

**公式（窗口 `[asOf - days, asOf]`）**

- `harvestKg` = 窗口内该室 `FlushHarvest.weight_kg` 之和（无记录为 0）
- `climateCount` = 窗口内该室 `ClimateLog` 条数
- `base = harvestKg / (capacityBags × days)`（每袋每日采收公斤）
- `utilizationHint`：`idle` → **强制 0**；`sanitize` → `base × 0.5`；`fruiting` → `base`

**接口**

- `GET /api/utilization` → `{ days, roomId, asOf, rooms: [{ roomId, roomCode, shedId, species, status, capacityBags, harvestKg, climateCount, utilizationHint }] }`
- `GET /api/utilization-check` → `{ days, roomId, asOf, rows: [...同上...], perRoom: { "<roomId>": { harvestKg, utilizationHint } } }`

**对账规则**：逐室比较两接口的 `harvestKg` 与 `utilizationHint`，绝对误差必须 **≤ 0.001**
（容差常量 `RECONCILE_TOLERANCE` 定义在 `services/utilization.py`）。
前端「利用率」页每次加载先并发请求两个接口、对账通过才渲染，失败则拒绝展示；
前端不本地计算 hint、不伪造公斤数，所有数值均来自接口。

**写路径一致性**：利用率按请求实时查询 `flush_harvests` / `climate_logs` 表（无缓存），
`POST /api/flush-harvests`、`POST /api/climate-logs` 提交成功后立刻反映到利用率与对账结果。

Seed 对照组：`R-01`/`V-01` fruiting（含窗口内采收，`R-01` 另有一条 10 天前记录用于验证窗口过滤）、
`R-02` idle（有采收记录但 hint 强制 0）、`V-02` sanitize（hint = 公式 × 0.5）。

## 前端页面

Login · Dashboard · Utilization（利用率对账看板） · Sheds · Rooms · ClimateLogs · FlushHarvests（侧边栏布局）

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

## 口径自检（可选）

无 docker 时可用 SQLite 跑一遍利用率口径与对账断言（38 项）：

```bash
cd backend
python3 verify_utilization.py   # 期望输出 ALL CHECKS PASSED
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
│       ├── services/
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
