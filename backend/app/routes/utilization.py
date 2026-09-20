from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.database import SessionLocal
from app.schemas.utilization import UtilizationBoardSchema, UtilizationCheckSchema
from app.services.utilization import (
    UtilizationParamsError,
    compute_utilization_rows,
    parse_utilization_params,
)

# 两个接口挂在同一蓝图、共用 _load_rows：
# /api/utilization 与 /api/utilization-check 是同一口径的两个视图，不是两套实现。
bp = Blueprint("utilization", __name__, url_prefix="/api")

board_schema = UtilizationBoardSchema()
check_schema = UtilizationCheckSchema()


def _load_rows():
    """解析筛选参数并按共享口径取数。返回 (payload_parts, error_response)。"""
    try:
        days, room_id, as_of = parse_utilization_params(request.args)
    except UtilizationParamsError as err:
        return None, (jsonify({"detail": str(err)}), 400)
    db = SessionLocal()
    try:
        rows = compute_utilization_rows(db, days=days, room_id=room_id, as_of=as_of)
    finally:
        db.close()
    return (days, room_id, as_of, rows), None


@bp.get("/utilization")
@jwt_required()
def get_utilization():
    loaded, err = _load_rows()
    if err:
        return err
    days, room_id, as_of, rows = loaded
    payload = {
        "days": days,
        "room_id": room_id,
        "as_of": as_of.isoformat(),
        "rooms": rows,
    }
    return jsonify(board_schema.dump(payload))


@bp.get("/utilization-check")
@jwt_required()
def get_utilization_check():
    loaded, err = _load_rows()
    if err:
        return err
    days, room_id, as_of, rows = loaded
    payload = {
        "days": days,
        "room_id": room_id,
        "as_of": as_of.isoformat(),
        "rows": rows,
        "per_room": {
            str(r["room_id"]): {
                "harvest_kg": r["harvest_kg"],
                "utilization_hint": r["utilization_hint"],
            }
            for r in rows
        },
    }
    return jsonify(check_schema.dump(payload))
