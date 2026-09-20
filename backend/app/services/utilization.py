"""出菇室利用率：主看板与对账接口共用的唯一口径。

两个对外接口（``/api/utilization`` 与 ``/api/utilization-check``）都必须经过本
模块取筛选条件与公式，禁止各写一套：

- 时间窗：``now - days`` 起（含），采收看 ``harvested_at``，环境看 ``recorded_at``，
  两个接口使用同一时间窗、同一室筛选。
- 每室产出：``harvestKg`` = 窗口内采收重量之和；``climateCount`` = 窗口内环境记录条数。
- ``utilizationHint`` 公式（``utilization_hint``）：
  ``base = harvestKg / capacityBags``；
  ``idle`` 室强制为 ``0``（即使窗口内有历史采收）；
  ``sanitize`` 室在 ``base`` 上再乘 ``0.5``；
  ``fruiting`` 室取 ``base``。

``_aggregate_sql``（SQL GROUP BY，主接口路径）与 ``_aggregate_rows``
（拉明细行后在 Python 端聚合，对账路径）共用同一筛选与公式，仅聚合手法不同，
逐室差异不得超过 ``HINT_TOLERANCE``。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from sqlalchemy import func

from app.models.climate_log import ClimateLog
from app.models.flush_harvest import FlushHarvest
from app.models.room import Room

DEFAULT_DAYS = 7
SANITIZE_FACTOR = 0.5
HINT_TOLERANCE = 0.001
KG_ROUND = 4
HINT_ROUND = 4


def parse_params(args) -> Tuple[int, Optional[int]]:
    """解析两个接口共用的查询参数：days（默认 7，正整数）与可选 roomId。"""
    days = args.get("days", default=DEFAULT_DAYS, type=int)
    if days is None or days <= 0:
        raise ValueError("days 须为正整数")
    room_id = args.get("roomId", type=int)
    return days, room_id


def utilization_hint(harvest_kg: float, capacity_bags: int, status: str) -> float:
    """唯一的 utilizationHint 公式，主接口与对账接口都调它。"""
    if status == "idle":
        # idle 室即使窗口内有采收也强制 0
        return 0.0
    hint = float(harvest_kg) / float(capacity_bags)
    if status == "sanitize":
        hint *= SANITIZE_FACTOR
    return round(hint, HINT_ROUND)


def _scope(db, days: int, room_id: Optional[int]):
    """同一份筛选：时间窗起点 + 室集合（可选 roomId）。"""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)
    rooms_q = db.query(Room)
    if room_id is not None:
        rooms_q = rooms_q.filter(Room.id == room_id)
    rooms = rooms_q.order_by(Room.id).all()
    return window_start, rooms


def _assemble(rooms, harvest_by_room, climate_by_room):
    """把任意聚合手法得到的两张 {room_id -> 数值} 表按同一公式装成每室结果。"""
    result = []
    for room in rooms:
        harvest_kg = round(float(harvest_by_room.get(room.id, 0.0) or 0.0), KG_ROUND)
        climate_count = int(climate_by_room.get(room.id, 0) or 0)
        result.append(
            {
                "room_id": room.id,
                "room_code": room.room_code,
                "species": room.species,
                "status": room.status,
                "capacity_bags": room.capacity_bags,
                "harvest_kg": harvest_kg,
                "climate_count": climate_count,
                "utilization_hint": utilization_hint(
                    harvest_kg, room.capacity_bags, room.status
                ),
            }
        )
    return result


def _aggregate_sql(db, window_start, rooms):
    """主接口路径：数据库 GROUP BY 聚合。"""
    ids = [r.id for r in rooms]
    if not ids:
        return []
    harvest_rows = (
        db.query(
            FlushHarvest.room_id,
            func.coalesce(func.sum(FlushHarvest.weight_kg), 0.0),
        )
        .filter(
            FlushHarvest.room_id.in_(ids),
            FlushHarvest.harvested_at >= window_start,
        )
        .group_by(FlushHarvest.room_id)
        .all()
    )
    climate_rows = (
        db.query(ClimateLog.room_id, func.count(ClimateLog.id))
        .filter(
            ClimateLog.room_id.in_(ids),
            ClimateLog.recorded_at >= window_start,
        )
        .group_by(ClimateLog.room_id)
        .all()
    )
    return _assemble(
        rooms, dict(harvest_rows), {rid: cnt for rid, cnt in climate_rows}
    )


def _aggregate_rows(db, window_start, rooms):
    """对账路径：用完全相同的筛选拉明细行，在 Python 端聚合。

    额外返回参与聚合的原始事件 ``rows``，便于逐笔追溯，而非只给聚合数。
    """
    ids = [r.id for r in rooms]
    if not ids:
        return [], []

    harvest_items = (
        db.query(FlushHarvest)
        .filter(
            FlushHarvest.room_id.in_(ids),
            FlushHarvest.harvested_at >= window_start,
        )
        .all()
    )
    climate_items = (
        db.query(ClimateLog)
        .filter(
            ClimateLog.room_id.in_(ids),
            ClimateLog.recorded_at >= window_start,
        )
        .all()
    )

    harvest_by_room: dict[int, float] = {}
    climate_by_room: dict[int, int] = {}
    events: list[dict[str, Any]] = []
    for item in harvest_items:
        harvest_by_room[item.room_id] = harvest_by_room.get(item.room_id, 0.0) + float(
            item.weight_kg
        )
        events.append(
            {
                "room_id": item.room_id,
                "kind": "harvest",
                "at": item.harvested_at,
                "weight_kg": float(item.weight_kg),
            }
        )
    for item in climate_items:
        climate_by_room[item.room_id] = climate_by_room.get(item.room_id, 0) + 1
        events.append(
            {
                "room_id": item.room_id,
                "kind": "climate",
                "at": item.recorded_at,
                "weight_kg": None,
            }
        )

    events.sort(key=lambda e: e["at"], reverse=True)
    return _assemble(rooms, harvest_by_room, climate_by_room), events


def _totals(per_room):
    return {
        "total_harvest_kg": round(
            sum(r["harvest_kg"] for r in per_room), KG_ROUND
        ),
        "total_climate_count": sum(r["climate_count"] for r in per_room),
    }


def build_utilization(db, days: int, room_id: Optional[int]) -> dict[str, Any]:
    """主看板口径：SQL GROUP BY 路径。"""
    window_start, rooms = _scope(db, days, room_id)
    per_room = _aggregate_sql(db, window_start, rooms)
    return {
        "days": days,
        "room_id": room_id,
        "window_start": window_start,
        "rooms": per_room,
        **_totals(per_room),
    }


def build_utilization_check(db, days: int, room_id: Optional[int]) -> dict[str, Any]:
    """对账口径：明细行聚合路径，并与主路径逐室比对。"""
    window_start, rooms = _scope(db, days, room_id)
    sql_per_room = _aggregate_sql(db, window_start, rooms)
    row_per_room, events = _aggregate_rows(db, window_start, rooms)

    sql_index = {r["room_id"]: r for r in sql_per_room}
    row_index = {r["room_id"]: r for r in row_per_room}

    mismatches = []
    max_harvest_diff = 0.0
    max_hint_diff = 0.0
    for rid in sorted(set(sql_index) | set(row_index)):
        a = sql_index.get(rid)
        b = row_index.get(rid)
        if a is None or b is None:
            mismatches.append({"room_id": rid, "reason": "室在两套结果中缺失其一"})
            continue
        harvest_diff = abs(a["harvest_kg"] - b["harvest_kg"])
        hint_diff = abs(a["utilization_hint"] - b["utilization_hint"])
        climate_diff = abs(a["climate_count"] - b["climate_count"])
        max_harvest_diff = max(max_harvest_diff, harvest_diff)
        max_hint_diff = max(max_hint_diff, hint_diff)
        if (
            harvest_diff > HINT_TOLERANCE
            or hint_diff > HINT_TOLERANCE
            or climate_diff != 0
        ):
            mismatches.append(
                {
                    "room_id": rid,
                    "harvest_diff": round(harvest_diff, KG_ROUND),
                    "hint_diff": round(hint_diff, HINT_ROUND),
                    "climate_diff": climate_diff,
                }
            )

    return {
        "days": days,
        "room_id": room_id,
        "window_start": window_start,
        "rows": events,
        "per_room": row_per_room,
        "reconciliation": {
            "tolerance": HINT_TOLERANCE,
            "max_harvest_kg_diff": round(max_harvest_diff, KG_ROUND),
            "max_hint_diff": round(max_hint_diff, HINT_ROUND),
            "passed": not mismatches,
            "mismatches": mismatches,
        },
    }
