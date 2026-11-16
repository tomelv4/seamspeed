# Helper: insert TEST_ bowling analyses for a single test device id (UI Progress testing); prints inserted ids
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
DEV = sys.argv[1]
PHASES = ["run_up", "load", "back_foot", "front_foot", "release", "follow_through"]


def doc(i, score, kmh):
    return {
        "device_id": DEV,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=3 - i)).isoformat(),
        "notes": "TEST_seed",
        "is_bowling_video": True,
        "overall_score": score,
        "summary": "TEST_ seeded bowling analysis",
        "action_type": "semi-open",
        "phases": [{"key": k, "name": k.replace("_", " ").title(), "score": score - 0.5 + j * 0.2, "feedback": "ok"} for j, k in enumerate(PHASES)],
        "faults": [{"title": "Falling away", "phase": "front_foot", "severity": "medium", "description": "d", "fix": "f"}],
        "strengths": ["Good rhythm"],
        "tips": ["Brace front leg"],
        "pace_band": {"label": "Fast-medium", "min_kmh": kmh - 5, "max_kmh": kmh + 5, "confidence": "low"},
        "injury_risk": {"level": "medium", "mixed_action": False, "counter_rotation": "moderate", "notes": "n"},
    }


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    res = await db.analyses.insert_many([doc(0, 6.0, 120), doc(1, 7.2, 128)])
    print([str(x) for x in res.inserted_ids])

asyncio.run(main())
