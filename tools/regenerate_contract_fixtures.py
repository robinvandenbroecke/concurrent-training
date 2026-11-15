"""Regenerate the frozen engine fixtures shared by the Python and TypeScript tests.

Run only for an intentional engine/contract change, bump ENGINE_VERSION (and
CONTRACT_VERSION for breaking changes), and review the diff:

    python tools/regenerate_contract_fixtures.py
"""
import json
from pathlib import Path

from app.science.contract import EngineRequest
from app.science.critical_power import w_prime_balance
from app.science.service import evaluate

TARGET = Path(__file__).resolve().parents[1] / "webapp" / "tests" / "fixtures" / "contracts"


def squat(day, shift, start=None):
    meta = {"metric": "mean_concentric", "deviceId": "manual-entry", "source": "manual"}
    sets = [{"setNum": i + 1, "weight": w, "completedReps": 1, "velocities": [round(1.30 - 0.008 * w + shift, 3)],
             "kind": "warmup", "velocityMeta": meta} for i, w in enumerate((40, 60, 80))]
    sets.append({"setNum": 4, "weight": 100, "completedReps": 3, "rpe": 8, "kind": "work", "velocityMeta": meta,
                 "velocities": [round(0.50 + shift, 3), None, round(0.42 + shift, 3)]})
    return {"id": f"fixture-squat-{day}", "date": day, "type": "kracht", "durationMinutes": 55, "startTime": start,
            "exercises": [{"exerciseId": "back_squat", "lift": "squat", "region": "lower", "sets": sets},
                          {"exerciseId": "clean_pull", "lift": "other", "power": True, "region": "full",
                           "sets": [{"setNum": 1, "weight": 70, "completedReps": 2, "velocities": [None, None], "rpe": 6}]},
                          {"exerciseId": "pull_up", "lift": "other", "loadType": "bodyweight", "region": "upper",
                           "sets": [{"setNum": 1, "weight": 0, "completedReps": 6, "velocities": [None] * 6}]}]}


def main():
    request = {
        "contractVersion": "1", "asOfDate": "2026-11-12",
        "endurance": {"maximalEfforts": [{"durationSeconds": t, "powerW": round(265 + 18000 / t, 1)} for t in (180, 360, 720, 1080)],
                      "thresholdPowerW": 250},
        "sessions": [squat("2026-10-20", 0.0), squat("2026-10-27", 0.01), squat("2026-11-03", -0.005),
                     squat("2026-11-10", -0.07, "2026-11-10T18:00:00+01:00"),
                     {"id": "fixture-ride-1", "date": "2026-11-10", "type": "duur", "durationMinutes": 40,
                      "startTime": "2026-11-10T16:30:00+01:00",
                      "enduranceResult": {"sport": "cycling", "durationMinutes": 40, "intensityType": "tempo",
                                          "power": {"sampleSeconds": 1, "watts": [210] * 1200 + [None] * 60 + [0] * 140 + [280] * 1000}}},
                     {"id": "fixture-run-1", "date": "2026-11-11", "type": "duur", "durationMinutes": 30,
                      "enduranceResult": {"sport": "running", "durationMinutes": 30, "intensityType": "easy", "rpe": 4}},
                     {"id": "fixture-ride-2", "date": "2026-11-05", "type": "duur", "durationMinutes": 60,
                      "enduranceResult": {"sport": "cycling", "durationMinutes": 60, "intensityType": "easy",
                                          "powerSummary": {"recordedSeconds": 3500, "missingSeconds": 100, "meanW": 180,
                                                           "sumSquaresW2s": 3500 * 185 ** 2}}},
                     {"id": "fixture-future", "date": "2026-11-20", "type": "duur", "durationMinutes": 30,
                      "enduranceResult": {"sport": "cycling", "durationMinutes": 30, "intensityType": "easy"}}],
    }
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "engine_v1_request.json").write_text(json.dumps(request, indent=1) + "\n")
    response = evaluate(EngineRequest.model_validate(request))
    (TARGET / "engine_v1_response.json").write_text(json.dumps(response, indent=1, allow_nan=False) + "\n")
    power = [150] * 60 + [400] * 90 + [120] * 120 + [None] * 5 + [380] * 60 + [0] * 30 + [250] * 30
    wbal = {"cp_w": 250, "w_prime_j": 18000, "dt_s": 1, "power_w": power,
            "expected_balance_j": w_prime_balance(power, 250, 18000, 1)}
    (TARGET / "wbal_v1.json").write_text(json.dumps(wbal) + "\n")


if __name__ == "__main__":
    main()
