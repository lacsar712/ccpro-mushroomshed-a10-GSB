from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.database import SessionLocal
from app.schemas.utilization import UtilizationCheckSchema, UtilizationStatsSchema
from app.services.utilization import (
    build_utilization,
    build_utilization_check,
    parse_params,
)

bp = Blueprint("utilization", __name__, url_prefix="/api")

stats_schema = UtilizationStatsSchema()
check_schema = UtilizationCheckSchema()


@bp.get("/utilization")
@jwt_required()
def get_utilization():
    db = SessionLocal()
    try:
        try:
            days, room_id = parse_params(request.args)
        except ValueError as exc:
            return jsonify({"detail": str(exc)}), 400
        payload = build_utilization(db, days, room_id)
        return jsonify(stats_schema.dump(payload))
    finally:
        db.close()


@bp.get("/utilization-check")
@jwt_required()
def get_utilization_check():
    db = SessionLocal()
    try:
        try:
            days, room_id = parse_params(request.args)
        except ValueError as exc:
            return jsonify({"detail": str(exc)}), 400
        payload = build_utilization_check(db, days, room_id)
        return jsonify(check_schema.dump(payload))
    finally:
        db.close()
