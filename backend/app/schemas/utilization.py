from marshmallow import Schema, fields


class UtilizationRoomSchema(Schema):
    room_id = fields.Int(data_key="roomId")
    room_code = fields.Str(data_key="roomCode")
    species = fields.Str()
    status = fields.Str()
    capacity_bags = fields.Int(data_key="capacityBags")
    harvest_kg = fields.Float(data_key="harvestKg")
    climate_count = fields.Int(data_key="climateCount")
    utilization_hint = fields.Float(data_key="utilizationHint")


class UtilizationStatsSchema(Schema):
    days = fields.Int()
    room_id = fields.Int(data_key="roomId", allow_none=True)
    window_start = fields.DateTime(data_key="windowStart")
    rooms = fields.List(fields.Nested(UtilizationRoomSchema))
    total_harvest_kg = fields.Float(data_key="totalHarvestKg")
    total_climate_count = fields.Int(data_key="totalClimateCount")


class UtilizationEventSchema(Schema):
    room_id = fields.Int(data_key="roomId")
    kind = fields.Str()
    at = fields.DateTime()
    weight_kg = fields.Float(data_key="weightKg", allow_none=True)


class ReconciliationMismatchSchema(Schema):
    room_id = fields.Int(data_key="roomId")
    reason = fields.Str(required=False)
    harvest_diff = fields.Float(data_key="harvestDiff", required=False)
    hint_diff = fields.Float(data_key="hintDiff", required=False)
    climate_diff = fields.Int(data_key="climateDiff", required=False)


class ReconciliationSchema(Schema):
    tolerance = fields.Float()
    max_harvest_kg_diff = fields.Float(data_key="maxHarvestKgDiff")
    max_hint_diff = fields.Float(data_key="maxHintDiff")
    passed = fields.Bool()
    mismatches = fields.List(fields.Nested(ReconciliationMismatchSchema))


class UtilizationCheckSchema(Schema):
    days = fields.Int()
    room_id = fields.Int(data_key="roomId", allow_none=True)
    window_start = fields.DateTime(data_key="windowStart")
    rows = fields.List(fields.Nested(UtilizationEventSchema))
    per_room = fields.List(fields.Nested(UtilizationRoomSchema), data_key="perRoom")
    reconciliation = fields.Nested(ReconciliationSchema)
