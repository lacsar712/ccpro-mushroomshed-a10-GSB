"""End-to-end verification of the utilization board (run with SQLite, no docker)."""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:////tmp/ms_util_test.db"
os.environ["JWT_SECRET"] = "test-secret"

if os.path.exists("/tmp/ms_util_test.db"):
    os.remove("/tmp/ms_util_test.db")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.database import Base, engine
from app import models  # noqa: F401  (register models)
from app.seed import seed

Base.metadata.create_all(bind=engine)
seed()

app = create_app()
c = app.test_client()

failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)


# --- auth ---
res = c.post("/api/auth/login", json={"username": "admin", "password": "123456"})
token = res.get_json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

res = c.get("/api/utilization")
check("utilization requires JWT (401)", res.status_code == 401)

# --- main endpoint, default days=7 ---
board = c.get("/api/utilization", headers=H).get_json()
check("default days == 7", board["days"] == 7, str(board["days"]))
check("roomId is null when unfiltered", board["roomId"] is None)
rooms = {r["roomCode"]: r for r in board["rooms"]}
check("4 seeded rooms returned", len(rooms) == 4, str(len(rooms)))

exp = {
    # roomCode: (harvestKg, climateCount, hint)
    "R-01": (80.5, 2, round(80.5 / (1200 * 7), 6)),
    "R-02": (12.0, 1, 0.0),                      # idle: hint forced 0 despite harvest
    "V-01": (55.2, 2, round(55.2 / (600 * 7), 6)),
    "V-02": (30.0, 1, round(30.0 / (500 * 7) * 0.5, 6)),  # sanitize: ×0.5
}
for code, (kg, cc, hint) in exp.items():
    r = rooms[code]
    check(f"{code} harvestKg == {kg}", abs(r["harvestKg"] - kg) < 1e-9, str(r["harvestKg"]))
    check(f"{code} climateCount == {cc}", r["climateCount"] == cc, str(r["climateCount"]))
    check(f"{code} hint == {hint}", abs(r["utilizationHint"] - hint) < 1e-9, str(r["utilizationHint"]))

check("R-02 idle hint forced 0 with harvestKg 12.0",
      rooms["R-02"]["harvestKg"] == 12.0 and rooms["R-02"]["utilizationHint"] == 0.0)

# --- check endpoint: same filters & formula, rows + perRoom ---
chk = c.get("/api/utilization-check", headers=H).get_json()
check("check returns rows and perRoom", "rows" in chk and "perRoom" in chk)
worst_kg = worst_hint = 0.0
for r in board["rooms"]:
    ref = chk["perRoom"][str(r["roomId"])]
    worst_kg = max(worst_kg, abs(ref["harvestKg"] - r["harvestKg"]))
    worst_hint = max(worst_hint, abs(ref["utilizationHint"] - r["utilizationHint"]))
check("per-room |ΔharvestKg| ≤ 0.001", worst_kg <= 0.001, f"worst={worst_kg}")
check("per-room |Δhint| ≤ 0.001", worst_hint <= 0.001, f"worst={worst_hint}")
check("check rows length matches rooms", len(chk["rows"]) == len(board["rooms"]))

# --- days=30 picks up the 10-day-old harvest on R-01 ---
b30 = c.get("/api/utilization?days=30", headers=H).get_json()
r1_30 = next(r for r in b30["rooms"] if r["roomCode"] == "R-01")
check("days=30 R-01 harvestKg == 110.5 (window filter works)",
      abs(r1_30["harvestKg"] - 110.5) < 1e-9, str(r1_30["harvestKg"]))
check("days=30 R-01 hint == 110.5/(1200*30)",
      abs(r1_30["utilizationHint"] - round(110.5 / 36000, 6)) < 1e-9)

# --- roomId filter ---
one = c.get("/api/utilization?roomId=2", headers=H).get_json()
check("roomId=2 returns only R-02", len(one["rooms"]) == 1 and one["rooms"][0]["roomCode"] == "R-02")
one_chk = c.get("/api/utilization-check?roomId=2", headers=H).get_json()
check("check endpoint honors roomId filter", len(one_chk["rows"]) == 1 and "2" in one_chk["perRoom"])

# --- asOf pinning: same value honored by both endpoints ---
pinned = "2026-09-19T12:00:00Z"
pa = c.get(f"/api/utilization?asOf={pinned}", headers=H).get_json()
pb = c.get(f"/api/utilization-check?asOf={pinned}", headers=H).get_json()
check("asOf echoed and identical", pa["asOf"] == pb["asOf"] and pa["asOf"].startswith("2026-09-19T12:00:00"))

# --- write path: new FlushHarvest reflected immediately ---
from datetime import datetime, timedelta, timezone

now_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
r2_id = rooms["R-02"]["roomId"]
res = c.post("/api/flush-harvests", headers=H, json={
    "roomId": r2_id, "harvestedAt": now_iso,
    "flushNo": 4, "weightKg": 5.0, "grade": "A", "operatorName": "验证员",
})
check("POST flush-harvest 201", res.status_code == 201, str(res.status_code))
after = c.get("/api/utilization", headers=H).get_json()
r2_after = next(r for r in after["rooms"] if r["roomCode"] == "R-02")
check("new harvest reflected immediately (12+5=17kg)",
      abs(r2_after["harvestKg"] - 17.0) < 1e-9, str(r2_after["harvestKg"]))
check("idle hint still forced 0 after write", r2_after["utilizationHint"] == 0.0)

# --- write path: new ClimateLog reflected immediately ---
v1_id = rooms["V-01"]["roomId"]
res = c.post("/api/climate-logs", headers=H, json={
    "roomId": v1_id, "recordedAt": now_iso,
    "tempC": 16.0, "humidityPct": 86, "co2Ppm": 700.0,
})
check("POST climate-log 201", res.status_code == 201, str(res.status_code))
after2 = c.get("/api/utilization", headers=H).get_json()
v1_after = next(r for r in after2["rooms"] if r["roomCode"] == "V-01")
check("new climate log reflected immediately (2+1=3)", v1_after["climateCount"] == 3)

# --- post-write reconciliation still holds ---
chk2 = c.get("/api/utilization-check", headers=H).get_json()
worst = max(
    max(abs(chk2["perRoom"][str(r["roomId"])]["harvestKg"] - r["harvestKg"]),
        abs(chk2["perRoom"][str(r["roomId"])]["utilizationHint"] - r["utilizationHint"]))
    for r in after2["rooms"]
)
check("post-write reconciliation ≤ 0.001", worst <= 0.001, f"worst={worst}")

# --- validation ---
check("days=0 -> 400", c.get("/api/utilization?days=0", headers=H).status_code == 400)
check("days=91 -> 400", c.get("/api/utilization?days=91", headers=H).status_code == 400)
check("days=abc -> 400", c.get("/api/utilization?days=abc", headers=H).status_code == 400)
check("roomId=abc -> 400", c.get("/api/utilization?roomId=abc", headers=H).status_code == 400)
check("asOf garbage -> 400", c.get("/api/utilization?asOf=nope", headers=H).status_code == 400)
check("check days=0 -> 400", c.get("/api/utilization-check?days=0", headers=H).status_code == 400)

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("ALL CHECKS PASSED")
