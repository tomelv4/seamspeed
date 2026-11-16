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

import hashlib

import emoji
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

import pose as pose_lib
from storage import APP_NAME, CACHE_DIR, cache_path, cached_file, init_storage, put_object
from emergentintegrations.llm.openai import OpenAITextToSpeech
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
    "poses": [IndexModel([("analysis_id", ASCENDING)], name="analysis_id")],
    "sessions": [IndexModel([("device_id", ASCENDING), ("created_at", DESCENDING)], name="device_created")],
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
    steps: List[dict] = []
    video_path: str = ""
    video_meta: dict = {}
    has_pose: bool = False


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

STEPS = [
    ("run_up_acceleration", "Run-Up Acceleration", "run_up", "Gradually building stride length and frequency to generate linear momentum."),
    ("peak_approach_velocity", "Peak Approach Velocity", "run_up", "Reaching maximum controllable running speed (5-7 m/s) while keeping the torso upright and eyes fixed on the target."),
    ("pre_delivery_stride", "Pre-Delivery Stride Adjustment", "run_up", "Shortening the penultimate stride slightly to prepare the body for takeoff."),
    ("take_off", "Take-Off (The Bound)", "load", "Pushing off the front foot into a low, forward-moving jump rather than jumping high."),
    ("gather", "The Gather", "load", "Pulling both hands close to the chest/chin while airborne to centre mass and maintain balance."),
    ("airborne_alignment", "Airborne Body Alignment", "load", "Coiling the hips and shoulders into a side-on, front-on, or semi-open position."),
    ("posterior_trunk_tilt", "Posterior Trunk Tilt", "load", "Leaning the upper body slightly backward away from the target to create a longer lever."),
    ("bfc", "Back-Foot Contact (BFC)", "back_foot", "Landing on the back foot and absorbing ground reaction forces of 2-3x body weight."),
    ("back_knee_compression", "Back-Knee Compression", "back_foot", "Slight bending of the back knee to absorb shock and load elastic energy like a spring."),
    ("counter_rotation", "Hip-Shoulder Counter-Rotation", "back_foot", "Locking the hips while slightly rotating the shoulders back to pre-stretch the core."),
    ("front_arm_elevation", "Front-Arm Elevation", "back_foot", "Raising the non-bowling arm high toward the sky to set up upper-body leverage."),
    ("delivery_stride", "Delivery Stride Extension", "front_foot", "Driving the front leg forward toward the batter while the bowling arm drops down and back."),
    ("ffc", "Front-Foot Contact (FFC)", "front_foot", "Planting the front heel firmly into the turf, absorbing peak forces of 5-9x body weight."),
    ("front_knee_bracing", "Front-Knee Bracing", "front_foot", "Locking or rapidly extending the front knee to abruptly brake the lower body and catapult the upper body forward."),
    ("pelvic_rotation", "Pelvic Rotation", "front_foot", "Driving the back hip violently forward toward the target while the shoulders remain delayed."),
    ("hip_shoulder_separation", "Hip-to-Shoulder Separation", "front_foot", "Stretching the oblique, abdominal, and pectoral muscles like a rubber band as the hips outpace the shoulders."),
    ("front_arm_pull_down", "Front-Arm Pull-Down", "release", "Pulling the non-bowling arm forcefully down toward the front hip to accelerate torso rotation."),
    ("lateral_trunk_flexion", "Lateral Trunk Flexion", "release", "Bending the torso sideways away from the bowling arm to allow a high release point."),
    ("forward_trunk_flexion", "Forward Trunk Flexion", "release", "Snapping the chest violently forward and downward over the braced front leg."),
    ("arm_circumduction", "Bowling Arm Circumduction", "release", "Whipping the bowling arm over the top in a fast vertical arc, keeping elbow extension within the legal 15-degree limit."),
    ("shoulder_internal_rotation", "Shoulder Internal Rotation", "release", "Rotating the upper arm inward at extreme speed just prior to release."),
    ("wrist_extension", "Wrist Extension (Cocking)", "release", "Pulling the wrist back slightly at the top of the arc to load the forearm flexors."),
    ("wrist_snap", "Wrist Snap (Flexion)", "release", "Snapping the wrist violently forward from extension into flexion at the exact point of release."),
    ("finger_roll_release", "Finger Roll & Ball Release", "release", "Rolling the index and middle fingers straight down the back of the ball to impart maximum backspin and speed."),
    ("arm_follow_through", "Arm Follow-Through & Deceleration", "follow_through", "Swinging the bowling arm all the way down across the front hip while the rotator cuff slows it down."),
    ("back_leg_swing", "Back-Leg Swing-Through", "follow_through", "Swinging the back leg forward past the braced front leg to carry remaining momentum down the pitch."),
    ("deceleration_strides", "Deceleration Strides", "follow_through", "Taking 3-5 balanced, curved running steps off the pitch to safely dissipate remaining forward kinetic energy."),
]
STEP_LIST_TEXT = "\n".join(f"{i + 1}. {k} - {n}: {d}" for i, (k, n, _, d) in enumerate(STEPS))

ANALYSIS_PROMPT = """You are an elite fast-bowling biomechanics coach (like a cricket version of SwingSensei for golf).
Analyse the attached video of a cricket pace bowler. Profile: {profile}. Extra notes from bowler: {notes}
The video is {duration} seconds long.

STEP-BY-STEP BIOMECHANICS: assess EVERY one of these 27 chronological steps and give the timestamp (seconds from the start of the video, 2 decimals) where it is best seen:
{steps}
For each step return {{"key","t","score" (0-10),"status" ("good"|"ok"|"fault"|"not_visible"),"observation" (what you see, 1-2 sentences),"cue" (one short coaching cue)}}.
Timestamps must be increasing. Use "not_visible" with t null if the step is out of frame.

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
 "steps": [{{"key":"run_up_acceleration","t":0.4,"score":7,"status":"good","observation":"...","cue":"..."}}, ... all 27 in order],
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
    data_bytes = await video.read()
    if len(data_bytes) > 80 * 1024 * 1024:
        raise HTTPException(413, "Clip too large - trim to one delivery")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data_bytes)
        path = tmp.name
    meta = await run_in_threadpool(pose_lib.video_meta, path)

    async def run_pose():
        try:
            return await run_in_threadpool(pose_lib.extract_pose, path)
        except Exception:
            logger.exception("pose extraction failed")
            return None

    async def run_gemini():
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"analysis-{uuid.uuid4()}",
            system_message="You are an expert cricket fast-bowling biomechanics analyst. Respond with JSON only.",
        ).with_model("gemini", "gemini-3-flash-preview")
        prompt = ANALYSIS_PROMPT.format(
            profile=f"{profile.name}, {profile.bowling_arm}-arm {profile.bowling_style}, {profile.level} level",
            notes=notes or "none",
            duration=meta.get("duration") or "unknown",
            steps=STEP_LIST_TEXT,
        )
        response = await chat.send_message(
            UserMessage(text=prompt, file_contents=[FileContentWithMimeType(file_path=path, mime_type=mime)])
        )
        return parse_json(response)

    try:
        pose_data, data = await asyncio.gather(run_pose(), run_gemini())
    except Exception as exc:
        logger.exception("analysis failed")
        with suppress(OSError):
            os.remove(path)
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}")

    # merge the 27 steps with definitions + measured joint angles
    by_key = {s.get("key"): s for s in data.get("steps", []) if isinstance(s, dict)}
    steps = []
    for key, name, phase, desc in STEPS:
        s = by_key.get(key, {})
        t = s.get("t")
        t = float(t) if isinstance(t, (int, float)) else None
        status = s.get("status", "not_visible")
        steps.append({
            "key": key, "name": name, "phase": phase, "description": desc, "t": t,
            "score": 0 if status == "not_visible" else s.get("score", 0), "status": status,
            "observation": s.get("observation", ""), "cue": s.get("cue", ""),
            "metrics": pose_lib.metrics_at(pose_data, t, profile.bowling_arm) if pose_data else {},
        })
    data["steps"] = steps

    video_path = f"{APP_NAME}/uploads/{x_device_id}/{uuid.uuid4()}{suffix}"
    try:
        await run_in_threadpool(put_object, video_path, data_bytes, mime)
        os.replace(path, cache_path(video_path))
    except Exception:
        logger.exception("video storage failed")
        video_path = ""
        with suppress(OSError):
            os.remove(path)

    data["video_path"] = video_path
    data["video_meta"] = {**meta, "width": (pose_data or {}).get("width", 0), "height": (pose_data or {}).get("height", 0), "mime": mime}
    data["has_pose"] = bool(pose_data and pose_data.get("detected"))

    analysis = Analysis(device_id=x_device_id, created_at=now_iso(), notes=notes, **{
        k: data[k] for k in Analysis.model_fields if k in data and k not in ("id", "device_id", "created_at", "notes")
    })
    result = await db.analyses.insert_one(analysis.to_mongo())
    analysis.id = str(result.inserted_id)
    if pose_data:
        await db.poses.insert_one({"analysis_id": analysis.id, "device_id": x_device_id, **pose_data})
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
    await db.poses.delete_many({"analysis_id": analysis_id})
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


# ---------------------------------------------------------------- pose + media
async def _owned_analysis(analysis_id: str, device_id: str) -> dict:
    if not ObjectId.is_valid(analysis_id):
        raise HTTPException(404, "Not found")
    doc = await db.analyses.find_one({"_id": ObjectId(analysis_id), "device_id": device_id})
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


@api_router.get("/analyses/{analysis_id}/pose")
async def get_pose(analysis_id: str, x_device_id: str = Header(...)):
    await _owned_analysis(analysis_id, x_device_id)
    doc = await db.poses.find_one({"analysis_id": analysis_id}, {"_id": 0, "analysis_id": 0, "device_id": 0})
    if not doc:
        raise HTTPException(404, "No body tracking for this clip")
    return doc


@api_router.get("/media/{analysis_id}")
async def get_media(analysis_id: str, d: str = Query(...), range_header: Optional[str] = Header(None, alias="range")):
    # Video players cannot send custom headers on web, so the device id comes as a query param.
    doc = await _owned_analysis(analysis_id, d)
    if not doc.get("video_path"):
        raise HTTPException(404, "No video stored")
    local = await run_in_threadpool(cached_file, doc["video_path"])
    mime = doc.get("video_meta", {}).get("mime", "video/mp4")
    size = local.stat().st_size
    match = re.match(r"bytes=(\d*)-(\d*)", range_header or "")
    if not match or (not match.group(1) and not match.group(2)):
        return FileResponse(local, media_type=mime, headers={"Accept-Ranges": "bytes"})
    start_s, end_s = match.groups()
    if start_s:
        start, end = int(start_s), min(int(end_s) if end_s else size - 1, size - 1)
    else:
        start, end = max(0, size - int(end_s)), size - 1
    if start >= size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    with open(local, "rb") as fh:
        fh.seek(start)
        chunk = fh.read(end - start + 1)
    return Response(content=chunk, status_code=206, media_type=mime, headers={
        "Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(len(chunk))})


# ---------------------------------------------------------------- TTS
tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
COACH_VOICE = "Energetic, encouraging professional cricket fast-bowling coach. Clear, punchy, motivating, natural pace."


def clean_for_tts(text: str) -> str:
    text = emoji.replace_emoji(text, replace="")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#>~|`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


async def speak(text: str) -> str:
    clean = clean_for_tts(text)[:4000]
    key = hashlib.sha256(f"{clean}|onyx|gpt-4o-mini-tts|mp3|{COACH_VOICE}".encode()).hexdigest()[:40]
    path = f"{APP_NAME}/tts/{key}.mp3"
    local = cache_path(path)
    if not local.exists():
        try:
            audio = await asyncio.wait_for(tts.generate_speech(text=clean, model="gpt-4o-mini-tts", voice="onyx", instructions=COACH_VOICE), 45)
        except Exception:
            logger.exception("tts primary failed, falling back")
            audio = await asyncio.wait_for(tts.generate_speech(text=clean, model="tts-1", voice="onyx"), 45)
        local.write_bytes(audio)
        with suppress(Exception):
            await run_in_threadpool(put_object, path, audio, "audio/mpeg")
        await db.tts.update_one({"key": key}, {"$set": {"key": key, "path": path}}, upsert=True)
    return key


@api_router.get("/tts/{key}.mp3")
async def get_tts(key: str):
    if not re.fullmatch(r"[a-f0-9]{40}", key):
        raise HTTPException(404, "Not found")
    path = f"{APP_NAME}/tts/{key}.mp3"
    if not cache_path(path).exists() and not await db.tts.find_one({"key": key}):
        raise HTTPException(404, "Not found")
    local = await run_in_threadpool(cached_file, path)
    return FileResponse(local, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=31536000"})


# ---------------------------------------------------------------- live coaching sessions
class Session(BaseDocument):
    device_id: str
    created_at: str
    focus: str
    status: str = "active"
    intro: str = ""
    intro_audio: str = ""
    balls: List[dict] = []
    summary: str = ""
    summary_audio: str = ""
    ended_at: str = ""


class SessionIn(BaseModel):
    focus: str = "Pace"


BALL_PROMPT = """You are watching ONE delivery from a live fast-bowling net session. Bowler: {profile}. Session focus: {focus}.
Current target from coach: {target}
Return ONLY JSON: {{"is_bowling": true, "score": 7.1, "pace_kmh": 128, "hit_target": true,
"good": "one thing done well", "fault": "the single most important fault (or empty)", "phase": "run_up|load|back_foot|front_foot|release|follow_through",
"injury_flag": false, "observation": "1-2 sentence technical observation"}}"""


async def coach_say(system: str, prompt: str) -> str:
    # Non-streaming: the full text is needed before it can be turned into speech.
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"session-{uuid.uuid4()}", system_message=system).with_model("openai", "gpt-5.5")
    return (await chat.send_message(UserMessage(text=prompt))).strip()


def coach_system(profile: Profile, focus: str) -> str:
    return (
        "You are PaceSensei, a live fast-bowling net coach speaking out loud to the bowler between deliveries. "
        "Talk like a real coach at the nets: short, punchy, specific, encouraging. Plain spoken English only, no lists, no markdown, no emojis. "
        f"Bowler: {profile.name}, {profile.bowling_arm}-arm {profile.bowling_style}, {profile.level}. Session focus: {focus}."
    )


async def _owned_session(session_id: str, device_id: str) -> Session:
    if not ObjectId.is_valid(session_id):
        raise HTTPException(404, "Not found")
    doc = await db.sessions.find_one({"_id": ObjectId(session_id), "device_id": device_id})
    if not doc:
        raise HTTPException(404, "Not found")
    return Session.from_mongo(doc)


@api_router.post("/sessions")
async def start_session(body: SessionIn, x_device_id: str = Header(...)):
    profile = await get_profile(x_device_id)
    recent = await db.analyses.find({"device_id": x_device_id, "is_bowling_video": True}).sort("created_at", -1).limit(1).to_list(1)
    faults = [f.get("title") for f in (recent[0].get("faults", []) if recent else [])]
    try:
        intro = await coach_say(coach_system(profile, body.focus),
            f"Start the session. Known faults from their last analysis: {faults or 'none yet'}. "
            "In under 55 words: greet them, say what we're working on today and give ONE clear target for the first ball. End with 'Bowl when ready.'")
        audio = await speak(intro)
    except Exception as exc:
        logger.exception("session start failed")
        raise HTTPException(502, f"Coach unavailable: {exc}")
    session = Session(device_id=x_device_id, created_at=now_iso(), focus=body.focus, intro=intro, intro_audio=audio)
    res = await db.sessions.insert_one(session.to_mongo())
    session.id = str(res.inserted_id)
    return session.public()


@api_router.get("/sessions")
async def list_sessions(x_device_id: str = Header(...)):
    docs = await db.sessions.find({"device_id": x_device_id}).sort("created_at", -1).limit(30).to_list(30)
    return [Session.from_mongo(d).public() for d in docs]


@api_router.get("/sessions/{session_id}")
async def get_session(session_id: str, x_device_id: str = Header(...)):
    return (await _owned_session(session_id, x_device_id)).public()


@api_router.post("/sessions/{session_id}/balls")
async def session_ball(session_id: str, video: UploadFile = File(...), x_device_id: str = Header(...)):
    session = await _owned_session(session_id, x_device_id)
    if session.status != "active":
        raise HTTPException(400, "Session already ended")
    profile = await get_profile(x_device_id)
    target = session.balls[-1]["next_target"] if session.balls else session.intro
    mime = video.content_type if (video.content_type or "").startswith("video/") else "video/mp4"
    suffix = Path(video.filename or "ball.mp4").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        ball_bytes = await video.read()
        if len(ball_bytes) > 80 * 1024 * 1024:
            raise HTTPException(413, "Clip too large - film one ball only")
        tmp.write(ball_bytes)
        path = tmp.name
    try:
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"ball-{uuid.uuid4()}",
                       system_message="Expert fast-bowling analyst. JSON only.").with_model("gemini", "gemini-3-flash-preview")
        raw = await chat.send_message(UserMessage(
            text=BALL_PROMPT.format(profile=f"{profile.bowling_arm}-arm {profile.bowling_style}", focus=session.focus, target=target),
            file_contents=[FileContentWithMimeType(file_path=path, mime_type=mime)]))
        obs = parse_json(raw)
        history = [{"n": b["n"], "score": b["score"], "fault": b.get("fault")} for b in session.balls[-5:]]
        speech = await coach_say(coach_system(profile, session.focus),
            f"Ball {len(session.balls) + 1} just bowled. Analysis: {json.dumps(obs)}. Previous balls: {json.dumps(history)}. "
            f"The target was: {target}. In under 50 words, speak your feedback (praise what was good, fix one thing), "
            "then on a new final line write exactly 'NEXT:' followed by the next short target for the next ball.")
        feedback, _, next_target = speech.partition("NEXT:")
        feedback, next_target = feedback.strip(), (next_target.strip() or "Same again, keep that rhythm.")
        audio = await speak(f"{feedback} Next ball: {next_target}")
    except Exception as exc:
        logger.exception("ball analysis failed")
        raise HTTPException(502, f"Coach could not review that ball: {exc}")
    finally:
        with suppress(OSError):
            os.remove(path)
    ball = {
        "n": len(session.balls) + 1, "created_at": now_iso(), "is_bowling": bool(obs.get("is_bowling", True)),
        "score": float(obs.get("score") or 0), "pace_kmh": obs.get("pace_kmh"), "hit_target": obs.get("hit_target"),
        "good": obs.get("good", ""), "fault": obs.get("fault", ""), "phase": obs.get("phase", ""),
        "injury_flag": bool(obs.get("injury_flag")), "observation": obs.get("observation", ""),
        "feedback": feedback, "next_target": next_target, "audio": audio,
    }
    await db.sessions.update_one({"_id": ObjectId(session_id)}, {"$push": {"balls": ball}})
    return ball


@api_router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, x_device_id: str = Header(...)):
    session = await _owned_session(session_id, x_device_id)
    if session.status == "ended":
        return session.public()
    profile = await get_profile(x_device_id)
    balls = [{"n": b["n"], "score": b["score"], "pace": b.get("pace_kmh"), "fault": b.get("fault"), "good": b.get("good")} for b in session.balls]
    try:
        summary = await coach_say(coach_system(profile, session.focus),
            f"The session is over. Balls: {json.dumps(balls)}. In under 80 words, wrap up: overall verdict, the biggest improvement, "
            "the one thing to work on before next session, and a motivating sign-off." if balls else
            "The bowler ended the session before bowling. In under 25 words, say no problem and invite them back.")
        audio = await speak(summary)
    except Exception as exc:
        logger.exception("session end failed")
        summary, audio = "Session saved. Great work today.", ""
    await db.sessions.update_one({"_id": ObjectId(session_id)}, {"$set": {
        "status": "ended", "summary": summary, "summary_audio": audio, "ended_at": now_iso()}})
    return (await _owned_session(session_id, x_device_id)).public()


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
    for fn in (init_storage, pose_lib.warmup):
        asyncio.get_event_loop().run_in_executor(None, _safe_call, fn)


def _safe_call(fn):
    try:
        fn()
    except Exception as exc:
        logging.getLogger(__name__).error("startup %s failed: %s", fn.__name__, exc)


@app.on_event("shutdown")
async def shutdown_db_client():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
