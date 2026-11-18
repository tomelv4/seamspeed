import asyncio
import json
import logging
import math
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
from analysis_contract import normalise_model_payload, parse_model_json, reconcile_synced_evidence
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
    "workload": [IndexModel([("device_id", ASCENDING), ("date", DESCENDING)], name="device_date")],
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
    age_band: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProfileIn(BaseModel):
    name: str
    bowling_arm: str
    bowling_style: str
    level: str
    age_band: str = ""

class Analysis(BaseDocument):
    device_id: str
    created_at: str
    notes: str = ""
    is_bowling_video: bool = True
    overall_score: float = 0
    overall_score_assessable: bool = True
    summary: str = ""
    action_type: str = ""
    camera_view: str = "unknown"
    camera_view_confidence: str = "low"
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
    events: dict = {}
    analysis_quality: dict = {}
    progress: dict = Field(default_factory=lambda: {"stage": "queued", "percent": 0, "message": "Waiting to start"})
    status: str = "done"  # processing | done | failed
    error: str = ""


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

from biomech import STEPS, STEP_LIST_TEXT  # noqa: E402
import biomech  # noqa: E402

ANALYSIS_PROMPT = """You are an elite fast-bowling biomechanics coach (like a cricket version of SwingSensei for golf).
Analyse the attached video of a cricket pace bowler. Profile: {profile}. Extra notes from bowler: {notes}
The video is {duration} seconds long.

STEP-BY-STEP BIOMECHANICS: assess EVERY one of these 27 chronological steps and give the timestamp (seconds from the start of the video, 2 decimals) where it is best seen:
{steps}
TECHNIQUE & LOAD OBSERVATIONS (not injury prediction):
- Describe only visible movement patterns that may be relevant to coaching. Do not diagnose tissue damage, infer internal forces,
  or predict injury probability from a single video.
- Do not infer spinal loading, side-strain risk, tendon loading, shoulder pathology or hamstring injury likelihood from 2D joint positions.
- If an area cannot be assessed from this camera angle, say so. Workload can only be assessed from the separately logged workload history.
For each step return {{"key","t","score" (0-10),"status" ("good"|"ok"|"fault"|"not_visible"),"coaching_classification" ("fault"|"opportunity"|"effective_variation"|"none"),"observation" (what you see, 1-2 sentences),"cue" (one short coaching cue)}}.
Timestamps must be increasing and each must be the exact moment described in WHEN (scrub frame by frame around
back-foot contact, front-foot contact and release). Use "not_visible" with t null if the step is out of frame.

EVIDENCE AND SCORING RULES:
- Never invent or guess a numeric angle, distance, speed, timing, joint position or ideal-range deviation.
- Quote a number only when it is explicitly supplied by measured skeleton data or is a clearly labelled visual estimate.
- A 2D skeleton value is a camera-plane estimate, not a 3D biomechanical measurement. Do not infer rotation, joint loading,
  legal elbow extension, ball speed, spin or injury probability from a single uncalibrated view.
- Actual ball release is the moment the ball visibly separates from the fingers. A wrist apex is not ball release.
  If separation is not clearly visible, mark finger_roll_release as not_visible with t null and score 0.
  Return release_evidence.ball_separation_visible=true only when the ball leaving the hand is clearly visible;
  also return confidence (high|medium|low) and a short note. If uncertain, return false and low confidence.
- Mark a step "not_visible" when the relevant body part or event cannot be judged reliably. Do not force a score.
- A scored step must have a timestamp that lands on the exact visible movement being judged. If you cannot identify that frame,
  return status "not_visible", t null, score 0 and do not write a technique judgement for that step.
- A fault must identify an exact step_key whose own status is "fault". Never attach a fault to a neighbouring or generic phase step.
  If no single step clearly supports the fault, omit it. Keep the description specific to what is visible at that moment.
- Phase feedback and the summary must be supported by assessable step observations. Do not introduce new faults or technique
  claims in the summary that are absent from the step evidence. Phase scores are calculated by the backend from assessable steps.
- For 3D rotation, ground-reaction force, angular velocity, ball spin, elbow legality or close-up finger/wrist mechanics,
  use "not_visible" unless the supplied footage and measurements genuinely support that assessment.
- The coaching reference text is qualitative guidance, not a set of universal numeric thresholds.
- "good", "ok" and "fault" require visible evidence; uncertainty is not a fault.
- Classify coaching significance separately from the status: "fault" = a clearly visible, materially important technical problem with a plausible downside; "opportunity" = an optional refinement that may help but is not proof the current movement is wrong; "effective_variation" = a non-textbook movement pattern that appears controlled or functional and has no clear visible downside; "none" = no specific coaching intervention justified.
- A non-standard action is not automatically a fault. Do not prescribe textbook positions as universal requirements. Only use "effective_variation" when the footage supports that it is controlled/effective; otherwise use "none" or "not_visible".
- Status "fault" is permitted only with coaching_classification "fault". Status "ok" may carry "opportunity" or "effective_variation". Do not manufacture opportunities just to fill the report.
- Scores should reflect only assessable technique. If several important steps are not assessable, lower confidence in
  the overall assessment and say so in the summary rather than filling gaps with assumptions.
- Use consistent step-score anchors: 0-2 = clear major breakdown; 3-4 = clear technical problem; 5-6 = mixed or
  inconsistent execution; 7-8 = controlled, repeatable execution; 9-10 = exceptional execution clearly supported by
  the footage. Do not award 9-10 merely because the action looks acceptable.
- Injury scanner outputs are coaching observations only, never a diagnosis or prediction. Do not label a medical injury
  risk high based on a single visual proxy. State when there is insufficient evidence.
- Do not estimate bowling speed from body motion or ball flight. Return pace_band with null min_kmh/max_kmh and
  confidence "unavailable" unless a calibrated speed source is provided.
- Do not report elbow-extension legality from 2D pose angles.

When identifying a fault, link it to the single most relevant step_key from the 27-step list. Do not invent a step key.
Break the action into 6 phases: run_up, load (bound/gather), back_foot (back-foot contact), front_foot (front-foot contact / delivery stride), release, follow_through.
Score each phase 0-10 (one decimal). Identify faults with severity (low|medium|high), linked phase key and a short fix.
Classify the visible action type as side-on, front-on, semi-open, mixed or unknown only when the view supports it. Separately classify the CAMERA VIEW as side_on, rear, front_on, oblique or unknown, and provide camera_view_confidence as high, medium or low. Do not infer 3D counter-rotation from a single 2D camera view.
Do not estimate bowling speed from run-up movement, arm speed or ball flight. A calibrated radar or ball-tracking measurement is required.

Return ONLY valid JSON, no markdown, matching exactly:
{{
 "is_bowling_video": true,
 "overall_score": 7.2,
 "summary": "2-3 sentence coach summary",
 "action_type": "semi-open",
 "camera_view": "side_on|rear|front_on|oblique|unknown",
 "camera_view_confidence": "high|medium|low",
 "release_evidence": {"ball_separation_visible": false, "confidence": "low", "notes": "Ball separation not clearly visible"},
 "phases": [{{"key":"run_up","name":"Run-up","score":7.5,"feedback":"..."}}, ... all 6 in order],
 "steps": [{{"key":"run_up_acceleration","t":0.4,"score":7,"status":"good","coaching_classification":"none","observation":"...","cue":"..."}}, ... all 27 in order],
 "faults": [{{"title":"Collapsing front knee","phase":"front_foot","step_key":"front_knee_bracing","severity":"medium","description":"...","fix":"..."}}],
 "strengths": ["..."],
 "tips": ["...", "...", "..."],
 "pace_band": {{"label":"Unavailable","min_kmh":null,"max_kmh":null,"confidence":"unavailable"}},
 "injury_risk": {{"level":"not_assessed","mixed_action":null,"counter_rotation":"not_assessed","notes":"A single video cannot predict injury likelihood.",
   "areas": [{{"key":"lumbar_spine|side_strain|front_leg|shoulder|hamstring_groin","level":"not_assessed","score":0,"drivers":"visible coaching observation only, or insufficient evidence","prevention":"general training guidance, not medical advice"}}, ... all 5 keys]}}
}}
If the video does not show a bowling action, set is_bowling_video to false, overall_score 0 and explain in summary."""

MEASURED_PROMPT = """

MEASURED SKELETON DATA of the tracked bowler (2D pose tracking at up to 60 fps):
{events}

Frame-by-frame timeline (angles in degrees; fk=front knee, bk=back knee, el=bowling elbow, lean=trunk lean from
vertical, hip_x=hip position across the frame 0-1):
{timeline}
Use event times as approximate anchors only. The event metadata includes the detection method and confidence.
Only use sagittal-plane knee, trunk-lean and stride measurements as coaching evidence when the camera view is side_on AND
camera_view_confidence is high. For rear, front-on, oblique or uncertain views, treat these side-plane values as unsuitable.
a wrist-apex proxy is not confirmed ball release, and ankle-ground heuristics are not force-plate contact measurements.
Use a measured value only when it is present and the relevant joints have adequate confidence. Do not fill absent values
with guessed numbers. Treat 2D angles as camera-plane estimates; do not infer 3D rotation or injury loading from them."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_profile(device_id: str) -> Profile:
    doc = await db.profiles.find_one({"device_id": device_id})
    return Profile.from_mongo(doc) if doc else Profile(device_id=device_id, updated_at="")


# ---------------------------------------------------------------- routes
@api_router.get("/")
async def root():
    return {"message": "PACED API"}


@api_router.get("/profile")
async def read_profile(x_device_id: str = Header(...)):
    return (await get_profile(x_device_id)).public()


@api_router.put("/profile")
async def update_profile(body: ProfileIn, x_device_id: str = Header(...)):
    if body.age_band and body.age_band not in WEEKLY_GUIDE:
        raise HTTPException(422, "Invalid age band")
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
    # Heavy work (pose tracking + Gemini Pro) runs in the background so the upload request returns
    # instantly instead of hitting the proxy timeout (502). The client polls GET /analyses/{id}.
    placeholder = Analysis(device_id=x_device_id, created_at=now_iso(), notes=notes, status="processing", is_bowling_video=False)
    result = await db.analyses.insert_one(placeholder.to_mongo())
    analysis_id = str(result.inserted_id)
    task = asyncio.create_task(process_analysis(analysis_id, path, data_bytes, mime, suffix, notes, x_device_id, profile))
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)
    return {"id": analysis_id, "status": "processing"}


_jobs: set = set()


async def process_analysis(analysis_id, path, data_bytes, mime, suffix, notes, x_device_id, profile):
    try:
        await _run_analysis(analysis_id, path, data_bytes, mime, suffix, notes, x_device_id, profile)
    except Exception as exc:
        logger.exception("analysis failed")
        with suppress(OSError):
            os.remove(path)
        await db.analyses.update_one(
            {"_id": ObjectId(analysis_id)},
            {"$set": {
                "status": "failed", "error": f"Analysis failed: {exc}",
                "progress": {"stage": "failed", "percent": 100, "message": "Analysis failed"},
            }},
        )


async def _run_analysis(analysis_id, path, data_bytes, mime, suffix, notes, x_device_id, profile):
    async def set_progress(stage: str, percent: int, message: str):
        await db.analyses.update_one(
            {"_id": ObjectId(analysis_id)},
            {"$set": {"progress": {"stage": stage, "percent": percent, "message": message}}},
        )

    await set_progress("preparing", 5, "Preparing your video")
    meta = await run_in_threadpool(pose_lib.video_meta, path)

    async def run_pose():
        try:
            return await run_in_threadpool(pose_lib.extract_pose, path)
        except Exception:
            logger.exception("pose extraction failed")
            return None

    async def run_gemini(pose_data):
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"analysis-{uuid.uuid4()}",
            system_message="You are an expert cricket fast-bowling biomechanics analyst. Respond with JSON only.",
        ).with_model("gemini", "gemini-3.1-pro-preview")
        prompt = ANALYSIS_PROMPT.format(
            profile=f"{profile.name}, {profile.bowling_arm}-arm {profile.bowling_style}, {profile.level} level",
            notes=notes or "none",
            duration=meta.get("duration") or "unknown",
            steps=STEP_LIST_TEXT,
            age=profile.age_band or "unknown",
        )
        if pose_data and pose_data.get("detected"):
            prompt += MEASURED_PROMPT.format(events=pre_text, timeline=pose_lib.timeline_text(pose_data, profile.bowling_arm, every=0.033))
        response = await chat.send_message(
            UserMessage(text=prompt, file_contents=[FileContentWithMimeType(file_path=path, mime_type=mime)])
        )
        return parse_model_json(response)

    await set_progress("tracking", 20, "Tracking your bowling action")
    pose_data = await run_pose()
    await set_progress("reviewing", 55, "Reviewing technique and movement")
    track = biomech.Track(pose_data or {}, profile.bowling_arm)
    pose_ev = biomech.detect_events(track)
    pre_ev = biomech.merge_events(pose_ev, [], meta.get("duration"))
    pre_text = biomech.measured_text(pre_ev, biomech.measured(track, pre_ev)) if pre_ev else "Key events could not be detected from the skeleton."
    pose_quality = (pose_data or {}).get("quality", {"rating": "limited", "frame_coverage": 0.0, "critical_joint_coverage": 0.0, "mean_joint_confidence": 0.0})
    data = normalise_model_payload(await run_gemini(pose_data), meta.get("duration"))
    await set_progress("report", 82, "Building your coaching report")
    camera_view = str(data.get("camera_view") or "unknown").strip().lower()
    if camera_view not in {"side_on", "rear", "front_on", "oblique", "unknown"}:
        camera_view = "unknown"
    data["camera_view"] = camera_view
    camera_view_confidence = str(data.get("camera_view_confidence") or "low").strip().lower()
    if camera_view_confidence not in {"high", "medium", "low"}:
        camera_view_confidence = "low"
    data["camera_view_confidence"] = camera_view_confidence

    # Never publish uncalibrated AI guesses as bowling speed or injury probability.
    data["pace_band"] = {
        "label": "Unavailable — calibrated speed measurement required",
        "min_kmh": None, "max_kmh": None, "confidence": "unavailable",
    }
    risk = data.get("injury_risk") if isinstance(data.get("injury_risk"), dict) else {}
    risk["level"] = "not_assessed"
    risk["mixed_action"] = None
    risk["counter_rotation"] = "not_assessed"
    risk["notes"] = (
        "A single-camera video cannot predict injury likelihood or diagnose a condition. "
        "Only visible coaching observations are shown; recorded workload is assessed separately."
    )
    risk["areas"] = [
        {**area, "level": "not_assessed", "score": 0}
        for area in risk.get("areas", []) if isinstance(area, dict)
    ]
    data["injury_risk"] = risk

    # sync every step to its biomechanical moment (measured events first, AI timestamps as fallback)
    ai_steps = data.get("steps", [])
    by_key = {s.get("key"): s for s in ai_steps if isinstance(s, dict)}
    release_evidence = data.get("release_evidence", {})
    if release_evidence.get("ball_separation_visible") is True and release_evidence.get("confidence") in {"high", "medium"}:
        # Prefer the AI's visible ball-separation timestamp over the wrist-apex proxy.
        pose_ev = dict(pose_ev)
        pose_ev.pop("release", None)
        for field in ("event_methods", "joint_confidence"):
            values = dict(pose_ev.get(field) or {})
            values.pop("release", None)
            pose_ev[field] = values
    ev = biomech.merge_events(pose_ev, ai_steps, meta.get("duration"))
    times = biomech.sync_times(ai_steps, ev) if ev else {}
    event_timing = biomech.event_timing_quality(ev, release_evidence)
    timing_rank = {"unavailable": 0, "low": 1, "medium": 2, "high": 3}
    meas = biomech.measured(track, ev) if ev and camera_view == "side_on" and camera_view_confidence == "high" else {}
    steps = []
    last_ai_time = 0.0
    for key, name, phase, when, ideal in STEPS:
        s = by_key.get(key, {})
        status = s.get("status", "not_visible")
        if status not in {"good", "ok", "fault", "not_visible"}:
            status = "not_visible"
        t = times.get(key)
        # Only use raw AI timestamps when no event anchors exist at all. If anchors exist,
        # sync_times returning None means the timestamp failed validation and must stay unavailable.
        if t is None and not ev:
            raw_t = biomech._valid_event_time(s.get("t"), meta.get("duration"))
            if raw_t is not None and raw_t >= last_ai_time:
                t = round(raw_t, 3)
                last_ai_time = raw_t
        raw_score = s.get("score", 0)
        score = float(raw_score) if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool) and math.isfinite(float(raw_score)) else 0.0
        score = max(0.0, min(10.0, score))
        observation = s.get("observation", "") if isinstance(s.get("observation", ""), str) else ""
        cue = s.get("cue", "") if isinstance(s.get("cue", ""), str) else ""
        anchor = biomech.WINDOWS[key][0]
        required_events = [anchor]
        if biomech.WINDOWS[key][2] is None and key in biomech.NEXT:
            required_events.append(biomech.NEXT[key][0])
        step_timing = min(
            (event_timing["events"].get(event, "unavailable") for event in required_events if event not in {"start", "end"}),
            key=lambda value: timing_rank[value],
            default="high",
        )
        steps.append({
            "key": key, "name": name, "phase": phase, "description": when, "ideal": ideal, "t": t,
            "score": 0 if status == "not_visible" else score, "status": status,
            "observation": observation, "cue": cue,
            "timing_confidence": step_timing,
            "timing_method": (ev or {}).get("event_methods", {}).get(anchor, "unavailable"),
            "metrics": meas.get(key, {}),
            "evidence_level": (
                "insufficient" if status == "not_visible"
                else "pose_estimate" if meas.get(key)
                else "visual_assessment" if observation
                else "insufficient"
            ),
        })
    data["steps"] = steps
    data = reconcile_synced_evidence(data)
    if ev:
        data["events"] = (
            {k: round(ev[k], 3) for k in ("take_off", "bfc", "ffc", "release")}
            | {"measured": ev["measured"], "pose_detected": ev.get("pose_detected", []),
               "estimated": ev.get("estimated", []), "sources": ev.get("sources", {}),
               "methods": ev.get("event_methods", {}), "confidence": ev.get("joint_confidence", {})}
        )

    await set_progress("saving", 95, "Saving your analysis")
    video_path = f"{APP_NAME}/uploads/{x_device_id}/{uuid.uuid4()}{suffix}"
    try:
        await run_in_threadpool(put_object, video_path, data_bytes, mime)
        os.replace(path, cache_path(video_path))
    except Exception:
        logger.exception("video storage failed")
        video_path = ""
        with suppress(OSError):
            os.remove(path)

    data["progress"] = {"stage": "complete", "percent": 100, "message": "Analysis complete"}
    data["video_path"] = video_path
    data["video_meta"] = {
        **meta,
        "width": (pose_data or {}).get("width") or meta.get("width", 0),
        "height": (pose_data or {}).get("height") or meta.get("height", 0),
        "mime": mime,
    }
    data["has_pose"] = bool(pose_data and pose_data.get("detected"))
    assessable_steps = sum(1 for step in steps if step["status"] != "not_visible")
    video_quality = meta.get("quality", {})
    capture_needs_review = video_quality.get("rating") != "good"
    score_confidence = (
        "low" if not data.get("overall_score_assessable", False) or pose_quality.get("rating") == "limited" or capture_needs_review
        else "medium" if assessable_steps < 19 or pose_quality.get("rating") != "good"
        else "high"
    )
    if timing_rank[event_timing["overall"]] < timing_rank[score_confidence]:
        score_confidence = "low" if event_timing["overall"] in {"low", "unavailable"} else event_timing["overall"]
    data["analysis_quality"] = {
        "score_confidence": score_confidence,
        "score_method": data.get("score_method", "not_available"),
        "camera_view": camera_view,
        "camera_view_confidence": camera_view_confidence,
        "assessable_steps": assessable_steps,
        "step_coverage": round(assessable_steps / max(1, len(steps)), 3),
        "pose": pose_quality,
        "video": video_quality,
        "event_methods": (ev or {}).get("event_methods", {}),
        "joint_confidence": (ev or {}).get("joint_confidence", {}),
        "contact_evidence": (pose_ev or {}).get("contact_evidence", {}),
        "event_timing": event_timing,
        "release_evidence": release_evidence,
        "limitations": [
            "Single-camera 2D pose estimates cannot establish 3D joint loading or rotation.",
            "Wrist apex is not confirmed ball release unless ball separation is visible.",
            "Bowling speed is unavailable without a calibrated measurement source.",
        ],
    }
    # Workload spikes are non-mechanical: computed from the bowler's logged volume, not the video.
    wl = await workload_summary(x_device_id, profile)
    risk = data.get("injury_risk") or {}
    areas = [a for a in risk.get("areas", []) if isinstance(a, dict) and a.get("key") != "workload"]
    areas.append({"key": "workload", "level": wl["status"], "score": {"low": 20, "medium": 55, "high": 85}[wl["status"]],
                  "drivers": wl["headline"], "prevention": wl["advice"]})
    risk["areas"] = areas
    data["injury_risk"] = risk

    fields = {k: data[k] for k in Analysis.model_fields if k in data and k not in ("id", "device_id", "created_at", "notes", "status", "error")}
    update = Analysis(device_id=x_device_id, created_at="", status="done", **fields).to_mongo()
    for k in ("device_id", "created_at", "notes"):
        update.pop(k, None)
    if pose_data:
        await db.poses.insert_one({"analysis_id": analysis_id, "device_id": x_device_id, **pose_data})
    await db.analyses.update_one({"_id": ObjectId(analysis_id)}, {"$set": update})


@api_router.get("/analyses")
async def list_analyses(x_device_id: str = Header(...), limit: int = Query(50, ge=1, le=200)):
    docs = await db.analyses.find({"device_id": x_device_id, "status": {"$nin": ["processing", "failed"]}}).sort("created_at", -1).limit(limit).to_list(limit)
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
        "score": a.overall_score if a.overall_score_assessable else None,
        "pace": ((a.pace_band.get("min_kmh") or 0) + (a.pace_band.get("max_kmh") or 0)) / 2 if a.pace_band else 0,
        "risk": a.injury_risk.get("level", "not_assessed"),
        "faults": len(a.faults),
    } for a in items]
    phase_avg = {}
    for key in PHASES:
        scores = [
            p.get("score") for a in items for p in a.phases
            if p.get("key") == key and p.get("assessable", True)
            and isinstance(p.get("score"), (int, float)) and math.isfinite(float(p.get("score")))
        ]
        phase_avg[key] = round(sum(scores) / len(scores), 1) if scores else None
    fault_counts: dict[str, int] = {}
    for a in items:
        for f in a.faults:
            fault_counts[f.get("title", "Unknown")] = fault_counts.get(f.get("title", "Unknown"), 0) + 1
    top_faults = sorted(fault_counts.items(), key=lambda x: -x[1])[:6]
    return {
        "points": points,
        "phase_avg": phase_avg,
        "top_faults": [{"title": t, "count": c} for t, c in top_faults],
        "best_score": max((p["score"] for p in points if p["score"] is not None), default=0),
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
         "You are PACED Coach, a world-class fast-bowling coach. Give concise, practical, encouraging advice "
        "(max ~150 words, short bullet points when listing). Prioritise sustainable technique, recovery and workload habits. "
        "Never diagnose injury or infer injury probability from a single delivery or uncalibrated video. "
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
    plan: dict = {}
    achievements: List[dict] = []
    test_result: dict = {}


# ---------------------------------------------------------------- workload tracker
from datetime import date as date_cls, timedelta  # noqa: E402

WEEKLY_GUIDE = {"Under 16": 120, "16-18": 180, "19-22": 240, "23+": 300}


class WorkloadIn(BaseModel):
    date: str  # YYYY-MM-DD
    balls: int = Field(ge=1, le=300)
    intensity: int = Field(default=7, ge=1, le=10)
    note: str = ""


async def add_balls(device_id: str, balls: int, source: str, intensity: int = 8, day: Optional[str] = None, note: str = ""):
    await db.workload.insert_one({"device_id": device_id, "date": day or date_cls.today().isoformat(), "balls": balls,
                                  "intensity": intensity, "source": source, "note": note, "created_at": now_iso()})


async def workload_summary(device_id: str, profile: Profile) -> dict:
    today = date_cls.today()
    start = (today - timedelta(days=55)).isoformat()
    docs = await db.workload.find({"device_id": device_id, "date": {"$gte": start}}).to_list(2000)
    daily: dict[str, int] = {}
    for d in docs:
        daily[d["date"]] = daily.get(d["date"], 0) + int(d["balls"])
    # Users ahead of UTC log "today" as tomorrow's UTC date - treat that as today.
    if daily.get((today + timedelta(days=1)).isoformat()):
        today = today + timedelta(days=1)
    day = lambda i: (today - timedelta(days=i)).isoformat()
    acute = sum(daily.get(day(i), 0) for i in range(7))
    prev_week = sum(daily.get(day(i), 0) for i in range(7, 14))
    chronic = sum(daily.get(day(i), 0) for i in range(28)) / 4
    first = min(daily.keys()) if daily else None
    enough_history = bool(first) and (today - date_cls.fromisoformat(first)).days >= 21
    acwr = round(acute / chronic, 2) if chronic and enough_history else None
    rest_days = sum(1 for i in range(7) if not daily.get(day(i)))
    streak = 0
    for i in range(0, 30):
        if daily.get(day(i)):
            streak += 1
        elif i > 0:
            break
    weeks = [{"label": (today - timedelta(days=7 * w + 6)).strftime("%d %b"),
              "balls": sum(daily.get(day(7 * w + i), 0) for i in range(7))} for w in range(7, -1, -1)]
    guide = WEEKLY_GUIDE.get(profile.age_band)
    flags = []
    if acwr is not None and acwr > 1.5:
        flags.append({"level": "high", "text": f"Acute:chronic ratio {acwr} - logged bowling volume is substantially above the recent 4-week baseline. Review intensity and recovery before adding more."})
    elif acwr is not None and acwr > 1.3:
        flags.append({"level": "medium", "text": f"Acute:chronic ratio {acwr} - logged bowling volume is above the recent baseline. Consider holding volume steady while monitoring recovery."})
    if prev_week and acute > prev_week * 1.3 and acute - prev_week >= 30:
        flags.append({"level": "medium" if acute < prev_week * 1.6 else "high", "text": f"Weekly spike: {acute} balls vs {prev_week} last week (+{round((acute / prev_week - 1) * 100)}%)."})
    if streak >= 4:
        flags.append({"level": "high" if streak >= 6 else "medium", "text": f"{streak} bowling days in a row - schedule a rest day."})
    if rest_days < 2 and acute:
        flags.append({"level": "medium", "text": f"Only {rest_days} rest day(s) in the last 7 days. Aim for at least 2."})
    if guide and acute > guide:
        flags.append({"level": "high", "text": f"{acute} balls this week exceeds the ~{guide}/week guide for the {profile.age_band} age band."})
    status = "high" if any(f["level"] == "high" for f in flags) else "medium" if flags else "low"
    headline = flags[0]["text"] if flags else (f"{acute} balls this week, {rest_days} rest days - no major workload flags in the logged data." if acute else "No bowling logged in the last 7 days.")
    advice = {"high": "Logged volume is well above recent baseline or a weekly guide. Consider reducing this week’s volume, prioritise recovery and seek individual advice if pain or unusual fatigue persists.",
              "medium": "Hold volume steady, plan recovery days and avoid a large jump in high-intensity deliveries.",
              "low": "Continue gradual progression, monitor how you feel and plan regular recovery days."}[status]
    return {"acute": acute, "previous_week": prev_week, "chronic_weekly": round(chronic, 1), "acwr": acwr, "rest_days_7": rest_days,
            "streak": streak, "weeks": weeks, "weekly_guide": guide, "flags": flags, "status": status, "headline": headline,
            "advice": advice, "today": daily.get(today.isoformat(), 0)}


@api_router.get("/workload")
async def get_workload(x_device_id: str = Header(...)):
    summary = await workload_summary(x_device_id, await get_profile(x_device_id))
    docs = await db.workload.find({"device_id": x_device_id}).sort([("date", -1), ("created_at", -1)]).limit(30).to_list(30)
    summary["entries"] = [{"id": str(d["_id"]), "date": d["date"], "balls": d["balls"], "intensity": d.get("intensity", 7),
                           "source": d.get("source", "manual"), "note": d.get("note", "")} for d in docs]
    return summary


@api_router.post("/workload")
async def log_workload(body: WorkloadIn, x_device_id: str = Header(...)):
    try:
        parsed = date_cls.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    if len(body.date) != 10 or parsed > date_cls.today() + timedelta(days=1) or parsed < date_cls.today() - timedelta(days=365):
        raise HTTPException(400, "date must be YYYY-MM-DD within the last year and not in the future")
    await add_balls(x_device_id, body.balls, "manual", body.intensity, parsed.isoformat(), body.note)
    return await get_workload(x_device_id)


@api_router.delete("/workload/{entry_id}")
async def delete_workload(entry_id: str, x_device_id: str = Header(...)):
    if not ObjectId.is_valid(entry_id):
        raise HTTPException(404, "Not found")
    res = await db.workload.delete_one({"_id": ObjectId(entry_id), "device_id": x_device_id})
    if not res.deleted_count:
        raise HTTPException(404, "Not found")
    return {"ok": True}


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=600)


@api_router.post("/speak")
async def speak_text(body: SpeakIn):
    return {"audio": await speak(body.text)}


class SessionIn(BaseModel):
    focus: str = "Pace"


BALL_PROMPT = """You are watching ONE delivery from a live fast-bowling net session. Bowler: {profile}. Session focus: {focus}.
Current target from coach: {target}
Assess only visible technique and target execution. Do not diagnose injury or infer injury risk.
Do not estimate bowling speed from body movement or uncalibrated video; pace_kmh must be null.
Return ONLY JSON: {{"is_bowling": true, "score": 7.1, "pace_kmh": null, "hit_target": true,
"good": "one thing done well", "fault": "the single most important visible technique fault (or empty)", "phase": "run_up|load|back_foot|front_foot|release|follow_through",
"observation": "1-2 sentence technical observation"}}"""


async def coach_say(system: str, prompt: str) -> str:
    # Non-streaming: the full text is needed before it can be turned into speech.
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"session-{uuid.uuid4()}", system_message=system).with_model("openai", "gpt-5.5")
    return (await chat.send_message(UserMessage(text=prompt))).strip()


def coach_system(profile: Profile, focus: str) -> str:
    return (
        "You are PACED, a live fast-bowling net coach speaking out loud to the bowler between deliveries. "
        "Talk like a real coach at the nets: short, punchy, specific, encouraging. Plain spoken English only, no lists, no markdown, no emojis. "
        "Focus on visible technique and sustainable training habits; do not diagnose injuries or estimate injury probability. "
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
    wl = await workload_summary(x_device_id, profile)
    try:
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"plan-{uuid.uuid4()}",
                       system_message=coach_system(profile, body.focus) + " When asked for JSON, return ONLY valid JSON.").with_model("openai", "gpt-5.5")
        raw = await chat.send_message(UserMessage(text=(
            f"Design today's complete fast-bowling net session. Focus: {body.focus}. Known faults: {faults or 'none yet'}. "
            f"Workload status: {wl['status']} ({wl['headline']}). If workload is high, keep bowling volume low and say why. "
            "Return JSON: {\"intro\": \"spoken greeting under 50 words that previews the session and ends with 'Let's start the warm-up.'\", "
            "\"warm_up\": [{\"name\": \"\", \"minutes\": 2, \"cue\": \"\"}] (5 dynamic items: jog, mobility, activation, build-up run-throughs, 3 easy deliveries), "
            "\"drills\": [{\"name\": \"\", \"reps\": \"3 x 8\", \"cue\": \"\"}] (3 technique drills targeting the faults/focus), "
            "\"bowling\": {\"balls\": 6-12, \"target\": \"first-ball target\"}, "
            "\"test\": {\"name\": \"\", \"balls\": 6, \"target\": \"what counts as a success\", \"description\": \"\"}, "
            "\"cool_down\": [{\"name\": \"\", \"minutes\": 2, \"cue\": \"\"}] (4 items incl. walk, hip flexor/hamstring/lumbar/shoulder stretches), "
            "\"tips\": [\"\", \"\", \"\"] (recovery, workload management and technique)}")))
        plan = parse_model_json(raw)
        intro = str(plan.pop("intro", "")).strip() or "Welcome to your PACED session. Let's start the warm-up."
        audio = await speak(intro)
    except Exception as exc:
        logger.exception("session start failed")
        raise HTTPException(502, f"Coach unavailable: {exc}")
    session = Session(device_id=x_device_id, created_at=now_iso(), focus=body.focus, intro=intro, intro_audio=audio, plan=plan)
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
async def session_ball(session_id: str, video: UploadFile = File(...), block: str = Form("bowling"), day: str = Form(""), x_device_id: str = Header(...)):
    session = await _owned_session(session_id, x_device_id)
    if session.status != "active":
        raise HTTPException(400, "Session already ended")
    profile = await get_profile(x_device_id)
    block = "test" if block == "test" else "bowling"
    block_balls = [b for b in session.balls if b.get("block", "bowling") == block]
    if block_balls:
        target = block_balls[-1]["next_target"]
    elif block == "test":
        target = (session.plan.get("test") or {}).get("target") or "Hit a good length on off stump"
    else:
        target = (session.plan.get("bowling") or {}).get("target") or session.intro
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
        obs = parse_model_json(raw)
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
        "score": float(obs.get("score") or 0), "pace_kmh": None, "hit_target": obs.get("hit_target"),
        "good": obs.get("good", ""), "fault": obs.get("fault", ""), "phase": obs.get("phase", ""),
        "observation": obs.get("observation", ""),
        "feedback": feedback, "next_target": next_target, "audio": audio, "block": block,
    }
    await db.sessions.update_one({"_id": ObjectId(session_id)}, {"$push": {"balls": ball}})
    if ball["is_bowling"]:
        local_day = None
        with suppress(ValueError):
            parsed = date_cls.fromisoformat(day)
            if len(day) == 10 and abs((parsed - date_cls.today()).days) <= 1:
                local_day = parsed.isoformat()
        await add_balls(x_device_id, 1, "session", 8, local_day)
    return ball


def compute_achievements(session: Session) -> tuple[list, dict]:
    balls = [b for b in session.balls if b.get("is_bowling", True)]
    test = [b for b in balls if b.get("block") == "test"]
    out = []
    add = lambda key, title, desc: out.append({"key": key, "title": title, "description": desc})
    if balls:
        add("session_complete", "Session Complete", f"{len(balls)} deliveries analysed")
    if len(balls) >= 6:
        add("full_over", "Full Over", "Bowled at least 6 tracked deliveries")
    streak = best = 0
    for b in balls:
        streak = streak + 1 if b.get("hit_target") else 0
        best = max(best, streak)
    if best >= 3:
        add("on_target", "On Target", f"Hit the coach's target {best} balls in a row")
    if len(balls) >= 4 and all(b["score"] >= 7 for b in balls):
        add("consistency", "Consistency", "Every ball scored 7 or higher")

    result = {}
    if test:
        hits = sum(1 for b in test if b.get("hit_target"))
        measured_paces = [b["pace_kmh"] for b in test if isinstance(b.get("pace_kmh"), (int, float)) and b["pace_kmh"] > 0]
        result = {"name": (session.plan.get("test") or {}).get("name", "Skills Test"), "balls": len(test), "hits": hits,
                  "avg_score": round(sum(b["score"] for b in test) / len(test), 1),
                  "top_pace": max(measured_paces) if measured_paces else None}
        if hits >= max(1, round(len(test) * 0.67)):
            add("test_passed", "Test Passed", f"{hits}/{len(test)} on target in the {result['name']}")
    return out, result


@api_router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, x_device_id: str = Header(...)):
    session = await _owned_session(session_id, x_device_id)
    if session.status == "ended":
        return session.public()
    profile = await get_profile(x_device_id)
    balls = [{"n": b["n"], "block": b.get("block", "bowling"), "score": b["score"], "pace": b.get("pace_kmh"), "fault": b.get("fault"), "good": b.get("good")} for b in session.balls]
    achievements, test_result = compute_achievements(session)
    try:
        summary = await coach_say(coach_system(profile, session.focus),
            f"The session is over (warm-up, drills, bowling block, test, cool-down). Balls: {json.dumps(balls)}. Test result: {json.dumps(test_result)}. "
            f"Achievements unlocked: {[a['title'] for a in achievements]}. In under 80 words, wrap up: overall verdict, the test result, "
            "the one thing to work on before next session, one recovery tip, and a motivating sign-off." if balls else
            "The bowler ended the session before bowling. In under 25 words, say no problem and invite them back.")
        audio = await speak(summary)
    except Exception as exc:
        logger.exception("session end failed")
        summary, audio = "Session saved. Great work today.", ""
    await db.sessions.update_one({"_id": ObjectId(session_id)}, {"$set": {
        "status": "ended", "summary": summary, "summary_audio": audio, "ended_at": now_iso(),
        "achievements": achievements, "test_result": test_result}})
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
    # background jobs die with the process: anything still "processing" at startup can never finish
    await db.analyses.update_many({"status": "processing"}, {"$set": {"status": "failed", "error": "The analysis was interrupted. Please upload the clip again."}})
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
