from marshmallow import Schema, fields


class UtilizationRoomSchema(Schema):
    room_id = fields.Int(data_key="roomId")
    room_code = fields.Str(data_key="roomCode")
    shed_id = fields.Int(data_key="shedId")
    species = fields.Str()
    status = fields.Str()
    capacity_bags = fields.Int(data_key="capacityBags")
    harvest_kg = fields.Float(data_key="harvestKg")
    climate_count = fields.Int(data_key="climateCount")
    utilization_hint = fields.Float(data_key="utilizationHint")


class UtilizationPerRoomSchema(Schema):
    harvest_kg = fields.Float(data_key="harvestKg")
    utilization_hint = fields.Float(data_key="utilizationHint")


class UtilizationBoardSchema(Schema):
    days = fields.Int()
    room_id = fields.Int(allow_none=True, data_key="roomId")
    as_of = fields.Str(data_key="asOf")
    rooms = fields.List(fields.Nested(UtilizationRoomSchema))


class UtilizationCheckSchema(Schema):
    days = fields.Int()
    room_id = fields.Int(allow_none=True, data_key="roomId")
    as_of = fields.Str(data_key="asOf")
    rows = fields.List(fields.Nested(UtilizationRoomSchema))
    per_room = fields.Dict(
        keys=fields.Str(),
        values=fields.Nested(UtilizationPerRoomSchema),
        data_key="perRoom",
    )
