# Seed ONE TEST_ analysis (device TEST_iter6_ui) in the real DB by running server._run_analysis with a synthetic
# pose and a mocked Gemini response, using /tmp/person.mp4 as the stored video. For UI testing of the 27-step card.
import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.path[:0] = ["/app/backend", "/app/backend/tests"]
import server  # noqa: E402
import biomech  # noqa: E402
from test_biomech_unit import synth_pose  # noqa: E402

DEV = "TEST_iter6_ui"
KEYS = [s[0] for s in biomech.STEPS]
AI = {"is_bowling_video": True, "overall_score": 5.8, "summary": "TEST_ seeded report for UI testing.", "action_type": "semi-open",
      "phases": [{"key": k, "name": k, "score": 6.0, "feedback": "f"} for k in ("run_up", "load", "back_foot", "front_foot", "release", "follow_through")],
      "steps": [{"key": k, "t": 0.1 + i * 0.07, "score": 4 + i % 6, "status": ["good", "ok", "fault"][i % 3],
                 "observation": f"Measured value vs ideal for {k} (TEST).", "cue": "Stay tall"} for i, k in enumerate(KEYS)],
      "faults": [{"title": "Front knee flex", "phase": "front_foot", "severity": "medium", "description": "d", "fix": "f"}],
      "strengths": ["s"], "tips": ["t"], "pace_band": {"label": "Medium", "min_kmh": 110, "max_kmh": 120, "confidence": "low"},
      "injury_risk": {"level": "low", "mixed_action": False, "counter_rotation": "low", "notes": "n", "areas": []}}


class Chat:
    def __init__(self, **kw):
        pass

    def with_model(self, *a):
        return self

    async def send_message(self, msg):
        return json.dumps(AI)


def pose_fn(p):
    d = synth_pose("right")
    d["width"], d["height"] = 640, 426
    return d


async def main():
    server.LlmChat = Chat
    server.pose_lib.extract_pose = pose_fn
    path = tempfile.mktemp(suffix=".mp4")
    shutil.copy("/tmp/person.mp4", path)
    data = open(path, "rb").read()
    ph = server.Analysis(device_id=DEV, created_at=server.now_iso(), notes="TEST_", status="processing", is_bowling_video=False)
    res = await server.db.analyses.insert_one(ph.to_mongo())
    aid = str(res.inserted_id)
    await server._run_analysis(aid, path, data, "video/mp4", ".mp4", "TEST_", DEV, server.Profile(device_id=DEV, updated_at=""))
    print("SEEDED", aid)


asyncio.run(main())
