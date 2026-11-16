import asyncio
import json
import logging
import os
import re
import tempfile
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, List, Optional

from bson import ObjectId
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware

from emergentintegrations.llm.chat import (
    FileContentWithMimeType,
    LlmChat,
    StreamDone,
    TextDelta,
    UserMessage,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']

INDEXES: dict[str, list[IndexModel]] = {
    "analyses": [IndexModel([("device_id", ASCENDING), ("created_at", DESCENDING)], name="device_created")],
    "profiles": [IndexModel([("device_id", ASCENDING)], name="device_id", unique=True)],
    "coach_messages": [IndexModel([("device_id", ASCENDING), ("created_at", ASCENDING)], name="device_created")],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:
                logging.getLogger(__name__).error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)


app = FastAPI()


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api_router = APIRouter(prefix="/api")

# ---------------------------------------------------------------- models
PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        return cls.model_validate(doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude={"id"})
        data.pop("_id", None)
        return data

    def public(self) -> dict:
        data = self.model_dump()
        return data


class Profile(BaseDocument):
    device_id: str
    name: str = "Bowler"
    bowling_arm: str = "Right"
    bowling_style: str = "Fast"
    level: str = "Club"
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProfileIn(BaseModel):
    name: str
    bowling_arm: str
    bowling_style: str
    level: str


class Analysis(BaseDocument):
    device_id: str
    created_at: str
    notes: str = ""
    is_bowling_video: bool = True
    overall_score: float = 0
    summary: str = ""
    action_type: str = ""
    phases: List[dict] = []
    faults: List[dict] = []
    strengths: List[str] = []
    tips: List[str] = []
    pace_band: dict = {}
    injury_risk: dict = {}


class CoachMessage(BaseDocument):
    device_id: str
    role: str
    content: str
    created_at: str


class ChatIn(BaseModel):
    message: str


# ---------------------------------------------------------------- drills library
PHASES = ["run_up", "load", "back_foot", "front_foot", "release", "follow_through"]

DRILLS: List[dict[str, Any]] = [
    {"id": "d1", "phase": "run_up", "title": "Rhythm Run-Up Markers", "duration": "10 min", "level": "Beginner",
     "fault_tags": ["inconsistent run-up", "stuttering", "overstriding"],
     "description": "Place cones at your mark, 5th and 10th stride. Build an even, accelerating rhythm without stutter steps.",
     "steps": ["Mark run-up with 3 cones", "Jog through 5 times at 60%", "Build to 90% keeping identical stride pattern", "Finish with 6 full-pace run-throughs"]},
    {"id": "d2", "phase": "run_up", "title": "Acceleration Ladder", "duration": "12 min", "level": "Intermediate",
     "fault_tags": ["slow approach", "decelerating"],
     "description": "Agility ladder work to train smooth acceleration into the crease.",
     "steps": ["Two-feet-in ladder x4", "Single-foot quick steps x4", "Ladder into 5-stride run-up x6"]},
    {"id": "d3", "phase": "load", "title": "Bound & Gather Freeze", "duration": "8 min", "level": "Beginner",
     "fault_tags": ["weak gather", "low jump", "collapsing load"],
     "description": "Practise a tall, controlled bound and freeze at the top of the gather to feel coil and alignment.",
     "steps": ["3-step approach into bound", "Freeze in coil position for 2s", "Check head over front arm", "Repeat x10"]},
    {"id": "d4", "phase": "load", "title": "Front-Arm Coil Drill", "duration": "6 min", "level": "All",
     "fault_tags": ["low front arm", "poor coil"],
     "description": "Standing drill to raise the front arm high and set a strong hip-shoulder separation.",
     "steps": ["Stand side-on", "Raise front arm, look behind it", "Pull down hard into release", "3 sets of 8"]},
    {"id": "d5", "phase": "back_foot", "title": "Back-Foot Alignment Line", "duration": "8 min", "level": "All",
     "fault_tags": ["mixed action", "back foot angle", "hip-shoulder mismatch"],
     "description": "Chalk line drill to align back foot, hips and shoulders and eliminate counter-rotation.",
     "steps": ["Draw line toward target", "Land back foot parallel to crease", "Hips & shoulders match", "Bowl 12 at 70%"]},
    {"id": "d6", "phase": "back_foot", "title": "Counter-Rotation Reset", "duration": "10 min", "level": "Intermediate",
     "fault_tags": ["counter-rotation", "mixed action", "back pain risk"],
     "description": "Reduce shoulder counter-rotation, the main driver of lumbar stress fractures in quicks.",
     "steps": ["Wall drill: shoulders stay matched to hips", "Walk-through deliveries", "Film from front-on and check"]},
    {"id": "d7", "phase": "front_foot", "title": "Brace the Front Leg", "duration": "10 min", "level": "Intermediate",
     "fault_tags": ["collapsing front knee", "soft front leg", "lost pace"],
     "description": "Develop a firm, braced front leg to transfer momentum into pace.",
     "steps": ["Step-and-brace holds x10", "Single-leg landings off box", "Bowl from 3 steps focusing on a straight front leg"]},
    {"id": "d8", "phase": "front_foot", "title": "Stride Length Cones", "duration": "8 min", "level": "All",
     "fault_tags": ["overstriding", "short stride", "falling away"],
     "description": "Find your optimal delivery stride length using cones.",
     "steps": ["Measure ~ 80% of height", "Place cone at landing spot", "Hit the cone 10 times in a row"]},
    {"id": "d9", "phase": "release", "title": "Seam Position Flicks", "duration": "6 min", "level": "Beginner",
     "fault_tags": ["wobbly seam", "poor wrist", "falling wrist"],
     "description": "Short-range flicks to a partner to grove an upright seam and firm wrist.",
     "steps": ["Kneel 5m from partner", "Flick ball with upright seam", "Progress to standing", "50 reps"]},
    {"id": "d10", "phase": "release", "title": "High Release Target", "duration": "10 min", "level": "Intermediate",
     "fault_tags": ["low release", "round arm", "dropping head"],
     "description": "Bowl over a raised marker to keep the release point high and head upright.",
     "steps": ["Place a pole at release height", "Bowl from 5 steps clearing marker", "Keep eyes level at release"]},
    {"id": "d11", "phase": "follow_through", "title": "Run-Through Finish", "duration": "6 min", "level": "All",
     "fault_tags": ["stopping short", "falling away", "abrupt finish"],
     "description": "Follow through fully toward the target to dissipate force and protect your back.",
     "steps": ["Bowl and run 5m past crease", "Keep chest facing target", "Repeat 12 deliveries"]},
    {"id": "d12", "phase": "follow_through", "title": "Hip Drive Medicine Ball", "duration": "12 min", "level": "Advanced",
     "fault_tags": ["weak hip drive", "lost pace", "arm-only bowling"],
     "description": "Explosive med-ball throws to train hip and trunk rotation through the crease.",
     "steps": ["3kg ball, side-on stance", "Drive hips and release overhead", "3 sets of 6 each side"]},
]

ANALYSIS_PROMPT = """You are an elite fast-bowling biomechanics coach (like a cricket version of SwingSensei for golf).
Analyse the attached video of a cricket pace bowler. Profile: {profile}. Extra notes from bowler: {notes}

Break the action into 6 phases: run_up, load (bound/gather), back_foot (back-foot contact), front_foot (front-foot contact / delivery stride), release, follow_through.
Score each phase 0-10 (one decimal). Identify faults with severity (low|medium|high), linked phase key and a short fix.
Classify the action type: side-on, front-on, semi-open, or mixed. Mixed actions (hip/shoulder mismatch, counter-rotation >30 deg) raise lumbar injury risk.
Estimate the pace band from approach speed, arm speed and ball flight (e.g. "125-135 km/h"). Be honest if uncertain.

Return ONLY valid JSON, no markdown, matching exactly:
{{
 "is_bowling_video": true,
 "overall_score": 7.2,
 "summary": "2-3 sentence coach summary",
 "action_type": "semi-open",
 "phases": [{{"key":"run_up","name":"Run-up","score":7.5,"feedback":"..."}}, ... all 6 in order],
 "faults": [{{"title":"Collapsing front knee","phase":"front_foot","severity":"medium","description":"...","fix":"..."}}],
 "strengths": ["..."],
 "tips": ["...", "...", "..."],
 "pace_band": {{"label":"Fast-medium","min_kmh":125,"max_kmh":135,"confidence":"medium"}},
 "injury_risk": {{"level":"low|medium|high","mixed_action":false,"counter_rotation":"low|moderate|high","notes":"..."}}
}}
If the video does not show a bowling action, set is_bowling_video to false, overall_score 0 and explain in summary."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_profile(device_id: str) -> Profile:
    doc = await db.profiles.find_one({"device_id": device_id})
    return Profile.from_mongo(doc) if doc else Profile(device_id=device_id, updated_at="")


def parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("No JSON in model response")
    return json.loads(match.group(0))


# ---------------------------------------------------------------- routes
@api_router.get("/")
async def root():
    return {"message": "PaceSensei API"}


@api_router.get("/profile")
async def read_profile(x_device_id: str = Header(...)):
    return (await get_profile(x_device_id)).public()


@api_router.put("/profile")
async def update_profile(body: ProfileIn, x_device_id: str = Header(...)):
    profile = Profile(device_id=x_device_id, **body.model_dump())
    await db.profiles.update_one({"device_id": x_device_id}, {"$set": profile.to_mongo()}, upsert=True)
    return (await get_profile(x_device_id)).public()


@api_router.post("/analyses")
async def create_analysis(
    video: UploadFile = File(...),
    notes: str = Form(""),
    x_device_id: str = Header(...),
):
    mime = video.content_type or "video/mp4"
    if not mime.startswith("video/"):
        mime = "video/mp4"
    suffix = Path(video.filename or "clip.mp4").suffix or ".mp4"
    profile = await get_profile(x_device_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await video.read())
        path = tmp.name
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"analysis-{uuid.uuid4()}",
            system_message="You are an expert cricket fast-bowling biomechanics analyst. Respond with JSON only.",
        ).with_model("gemini", "gemini-3-flash-preview")
        prompt = ANALYSIS_PROMPT.format(
            profile=f"{profile.name}, {profile.bowling_arm}-arm {profile.bowling_style}, {profile.level} level",
            notes=notes or "none",
        )
        response = await chat.send_message(
            UserMessage(text=prompt, file_contents=[FileContentWithMimeType(file_path=path, mime_type=mime)])
        )
        data = parse_json(response)
    except Exception as exc:
        logger.exception("analysis failed")
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}")
    finally:
        with suppress(OSError):
            os.remove(path)

    analysis = Analysis(device_id=x_device_id, created_at=now_iso(), notes=notes, **{
        k: data[k] for k in Analysis.model_fields if k in data and k not in ("id", "device_id", "created_at", "notes")
    })
    result = await db.analyses.insert_one(analysis.to_mongo())
    analysis.id = str(result.inserted_id)
    return analysis.public()


@api_router.get("/analyses")
async def list_analyses(x_device_id: str = Header(...), limit: int = Query(50, ge=1, le=200)):
    docs = await db.analyses.find({"device_id": x_device_id}).sort("created_at", -1).limit(limit).to_list(limit)
    return [Analysis.from_mongo(d).public() for d in docs]


@api_router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, x_device_id: str = Header(...)):
    if not ObjectId.is_valid(analysis_id):
        raise HTTPException(404, "Not found")
    doc = await db.analyses.find_one({"_id": ObjectId(analysis_id), "device_id": x_device_id})
    if not doc:
        raise HTTPException(404, "Not found")
    return Analysis.from_mongo(doc).public()


@api_router.delete("/analyses/{analysis_id}")
async def delete_analysis(analysis_id: str, x_device_id: str = Header(...)):
    if not ObjectId.is_valid(analysis_id):
        raise HTTPException(404, "Not found")
    res = await db.analyses.delete_one({"_id": ObjectId(analysis_id), "device_id": x_device_id})
    if not res.deleted_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@api_router.get("/drills")
async def list_drills(phase: Optional[str] = None, x_device_id: str = Header(...)):
    latest = await db.analyses.find_one({"device_id": x_device_id, "is_bowling_video": True}, sort=[("created_at", -1)])
    fault_phases = {f.get("phase") for f in (latest or {}).get("faults", [])}
    drills = [d for d in DRILLS if not phase or d["phase"] == phase]
    out = [{**d, "recommended": d["phase"] in fault_phases} for d in drills]
    out.sort(key=lambda d: not d["recommended"])
    return out


@api_router.get("/drills/{drill_id}")
async def get_drill(drill_id: str):
    for d in DRILLS:
        if d["id"] == drill_id:
            return d
    raise HTTPException(404, "Not found")


@api_router.get("/progress")
async def progress(x_device_id: str = Header(...)):
    docs = await db.analyses.find({"device_id": x_device_id, "is_bowling_video": True}).sort("created_at", 1).to_list(200)
    items = [Analysis.from_mongo(d) for d in docs]
    points = [{
        "id": a.id,
        "date": a.created_at,
        "score": a.overall_score,
        "pace": ((a.pace_band.get("min_kmh") or 0) + (a.pace_band.get("max_kmh") or 0)) / 2 if a.pace_band else 0,
        "risk": a.injury_risk.get("level", "low"),
        "faults": len(a.faults),
    } for a in items]
    phase_avg = {}
    for key in PHASES:
        scores = [p.get("score", 0) for a in items for p in a.phases if p.get("key") == key]
        phase_avg[key] = round(sum(scores) / len(scores), 1) if scores else 0
    fault_counts: dict[str, int] = {}
    for a in items:
        for f in a.faults:
            fault_counts[f.get("title", "Unknown")] = fault_counts.get(f.get("title", "Unknown"), 0) + 1
    top_faults = sorted(fault_counts.items(), key=lambda x: -x[1])[:6]
    return {
        "points": points,
        "phase_avg": phase_avg,
        "top_faults": [{"title": t, "count": c} for t, c in top_faults],
        "best_score": max((p["score"] for p in points), default=0),
        "best_pace": max(((a.pace_band or {}).get("max_kmh") or 0 for a in items), default=0),
        "total": len(points),
    }


# ---------------------------------------------------------------- AI coach (ChatGPT)
@api_router.get("/coach/messages")
async def coach_messages(x_device_id: str = Header(...)):
    docs = await db.coach_messages.find({"device_id": x_device_id}).sort("created_at", 1).to_list(200)
    return [CoachMessage.from_mongo(d).public() for d in docs]


@api_router.delete("/coach/messages")
async def clear_coach(x_device_id: str = Header(...)):
    await db.coach_messages.delete_many({"device_id": x_device_id})
    return {"ok": True}


@api_router.post("/coach/chat")
async def coach_chat(body: ChatIn, x_device_id: str = Header(...)):
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "Message required")
    profile = await get_profile(x_device_id)
    recent = await db.analyses.find({"device_id": x_device_id, "is_bowling_video": True}).sort("created_at", -1).limit(3).to_list(3)
    context = [
        {"date": a["created_at"][:10], "score": a.get("overall_score"), "action": a.get("action_type"),
         "pace": a.get("pace_band", {}).get("label"), "risk": a.get("injury_risk", {}).get("level"),
         "faults": [f.get("title") for f in a.get("faults", [])]}
        for a in recent
    ]
    history = await db.coach_messages.find({"device_id": x_device_id}).sort("created_at", -1).limit(12).to_list(12)
    history.reverse()
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)

    system = (
        "You are PaceSensei Coach, a world-class fast-bowling coach. Give concise, practical, encouraging advice "
        "(max ~150 words, short bullet points when listing). Prioritise injury prevention for young quicks. "
        f"Bowler: {profile.name}, {profile.bowling_arm}-arm {profile.bowling_style}, {profile.level}. "
        f"Recent analyses: {json.dumps(context)}. "
        f"Conversation so far:\n{transcript}"
    )
    await db.coach_messages.insert_one(CoachMessage(device_id=x_device_id, role="user", content=text, created_at=now_iso()).to_mongo())

    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"coach-{uuid.uuid4()}", system_message=system).with_model("openai", "gpt-5.5")

    async def events():
        full = ""
        try:
            async for ev in chat.stream_message(UserMessage(text=text)):
                if isinstance(ev, TextDelta):
                    full += ev.content
                    yield f"data: {json.dumps({'delta': ev.content})}\n\n"
                elif isinstance(ev, StreamDone):
                    break
        except Exception as exc:
            logger.exception("coach failed")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        if full:
            await db.coach_messages.insert_one(CoachMessage(device_id=x_device_id, role="assistant", content=full, created_at=now_iso()).to_mongo())
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def start_index_build():
    app.state.index_task = asyncio.create_task(ensure_indexes())


@app.on_event("shutdown")
async def shutdown_db_client():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
