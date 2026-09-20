"""出菇室利用率口径（唯一实现）。

/api/utilization 与 /api/utilization-check 都从这里取数，
保证两个接口的筛选与公式完全一致（同一口径，不允许两套各写）。

口径定义（与 README「利用率看板与对账口径」一节保持一致）：

- 窗口：[as_of - days, as_of]，右端 as_of 默认取当前时间（UTC），
  前端对账时显式传同一个 asOf，保证两次请求窗口完全一致。
- harvestKg(room)   = 窗口内该室 FlushHarvest.weight_kg 之和（无记录为 0）。
- climateCount(room)= 窗口内该室 ClimateLog 条数（无记录为 0）。
- base(room)        = harvestKg / (capacityBags × days)   # 每袋每日采收公斤
- utilizationHint：
    status == "idle"     -> 0.0（强制，无论是否有采收）
    status == "sanitize" -> base × 0.5
    其他（fruiting）     -> base
- 对账容差 RECONCILE_TOLERANCE = 0.001（逐室 |ΔharvestKg|、|Δhint|）。
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.models.climate_log import ClimateLog
from app.models.flush_harvest import FlushHarvest
from app.models.room import Room

DEFAULT_DAYS = 7
MIN_DAYS = 1
MAX_DAYS = 90
SANITIZE_FACTOR = 0.5
RECONCILE_TOLERANCE = 0.001

# 出菇室状态（与 schemas/room.py ROOM_STATUSES 对齐）
STATUS_FRUITING = "fruiting"
STATUS_IDLE = "idle"
STATUS_SANITIZE = "sanitize"


class UtilizationParamsError(ValueError):
    """筛选参数非法（路由层转成 400）。"""


def _parse_days(raw) -> int:
    if raw is None or raw == "":
        return DEFAULT_DAYS
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise UtilizationParamsError("days 必须是整数")
    if not (MIN_DAYS <= days <= MAX_DAYS):
        raise UtilizationParamsError(f"days 必须在 {MIN_DAYS}-{MAX_DAYS} 之间")
    return days


def _parse_room_id(raw):
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise UtilizationParamsError("roomId 必须是整数")


def _parse_as_of(raw) -> datetime:
    if raw is None or raw == "":
        return datetime.now(timezone.utc)
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise UtilizationParamsError("asOf 必须是 ISO 8601 时间")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_utilization_params(args):
    """解析两个接口共用的筛选参数：days / roomId / asOf。"""
    days = _parse_days(args.get("days"))
    room_id = _parse_room_id(args.get("roomId"))
    as_of = _parse_as_of(args.get("asOf"))
    return days, room_id, as_of


def utilization_hint(status: str, capacity_bags: int, harvest_kg: float, days: int) -> float:
    """利用率提示值。idle 强制 0；sanitize 按采收公式再乘 0.5。"""
    if status == STATUS_IDLE:
        return 0.0
    base = harvest_kg / (capacity_bags * days)
    if status == STATUS_SANITIZE:
        base *= SANITIZE_FACTOR
    return round(base, 6)


def compute_utilization_rows(db, days: int, room_id=None, as_of: datetime | None = None):
    """按口径计算每室一行。两个接口共用这同一个函数。"""
    as_of = as_of or datetime.now(timezone.utc)
    since = as_of - timedelta(days=days)

    q = db.query(Room)
    if room_id is not None:
        q = q.filter(Room.id == room_id)
    rooms = q.order_by(Room.id).all()

    room_ids = [r.id for r in rooms]
    harvest_map = {}
    climate_map = {}
    if room_ids:
        harvest_rows = (
            db.query(
                FlushHarvest.room_id,
                func.coalesce(func.sum(FlushHarvest.weight_kg), 0.0),
            )
            .filter(
                FlushHarvest.room_id.in_(room_ids),
                FlushHarvest.harvested_at >= since,
                FlushHarvest.harvested_at <= as_of,
            )
            .group_by(FlushHarvest.room_id)
            .all()
        )
        harvest_map = {rid: float(total) for rid, total in harvest_rows}

        climate_rows = (
            db.query(ClimateLog.room_id, func.count(ClimateLog.id))
            .filter(
                ClimateLog.room_id.in_(room_ids),
                ClimateLog.recorded_at >= since,
                ClimateLog.recorded_at <= as_of,
            )
            .group_by(ClimateLog.room_id)
            .all()
        )
        climate_map = {rid: int(cnt) for rid, cnt in climate_rows}

    rows = []
    for room in rooms:
        harvest_kg = round(harvest_map.get(room.id, 0.0), 6)
        rows.append(
            {
                "room_id": room.id,
                "room_code": room.room_code,
                "shed_id": room.shed_id,
                "species": room.species,
                "status": room.status,
                "capacity_bags": room.capacity_bags,
                "harvest_kg": harvest_kg,
                "climate_count": climate_map.get(room.id, 0),
                "utilization_hint": utilization_hint(
                    room.status, room.capacity_bags, harvest_kg, days
                ),
            }
        )
    return rows
