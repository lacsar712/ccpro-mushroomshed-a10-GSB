export type RoomStatus = 'fruiting' | 'idle' | 'sanitize'
export type HarvestGrade = 'A' | 'B' | 'C'

export interface Shed {
  id: number
  name: string
  location: string
  notes?: string | null
}

export interface Room {
  id: number
  shedId: number
  roomCode: string
  species: string
  capacityBags: number
  status: RoomStatus
}

export interface ClimateLog {
  id: number
  roomId: number
  recordedAt: string
  tempC: number
  humidityPct: number
  co2Ppm?: number | null
  notes?: string | null
}

export interface FlushHarvest {
  id: number
  roomId: number
  harvestedAt: string
  flushNo: number
  weightKg: number
  grade: HarvestGrade
  operatorName: string
}

export interface DashboardStats {
  shedTotal: number
  fruitingRoomCount: number
  climateLast24h: number
  harvestKgLast7d: number
}

export interface UtilizationRoom {
  roomId: number
  roomCode: string
  species: string
  status: RoomStatus
  capacityBags: number
  harvestKg: number
  climateCount: number
  utilizationHint: number
}

export interface UtilizationResponse {
  days: number
  roomId: number | null
  windowStart: string
  rooms: UtilizationRoom[]
  totalHarvestKg: number
  totalClimateCount: number
}

export interface UtilizationEvent {
  roomId: number
  kind: 'harvest' | 'climate'
  at: string
  weightKg: number | null
}

export interface Reconciliation {
  tolerance: number
  maxHarvestKgDiff: number
  maxHintDiff: number
  passed: boolean
  mismatches: Array<{
    roomId?: number
    reason?: string
    harvestDiff?: number
    hintDiff?: number
    climateDiff?: number
  }>
}

export interface UtilizationCheckResponse {
  days: number
  roomId: number | null
  windowStart: string
  rows: UtilizationEvent[]
  perRoom: UtilizationRoom[]
  reconciliation: Reconciliation
}
