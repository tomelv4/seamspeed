import { useQuery } from "@tanstack/react-query";
import { fetch as expoFetch } from "expo/fetch";
import { Platform } from "react-native";

import { uploadForm } from "@/src/utils/upload";
import { storage } from "@/src/utils/storage";

export const API = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

export type Phase = { key: string; name: string; score: number; feedback: string; assessable?: boolean };
export type Fault = { title: string; phase: string; step_key?: string; severity: "low" | "medium" | "high"; description: string; fix: string };
export type CoachingPriority = {
  priority: number; type: "fault" | "opportunity"; step_key: string; phase: string;
  title: string; reason: string; action: string; severity: "low" | "medium" | "high" | null;
  why_it_matters?: string; feel_cue?: string; drill?: string; success_check?: string;
  drill_name?: string; drill_setup?: string; drill_action?: string; drill_dose?: string;
};
export type DrillPracticeHistory = {
  total_completions: number;
  focuses: { step_key: string; focus: string; drill_name: string; completed_count: number; last_completed_at: string; recent_sessions: { completed_at: string; notes: string; analysis_id: string }[] }[];
  sessions: { id: string; analysis_id: string; step_key: string; focus: string; drill_name: string; completed_at: string; notes: string }[];
};
export type AnalysisProgress = { stage?: string; percent?: number; message?: string };
export type Analysis = {
  id: string;
  status?: "processing" | "done" | "failed";
  progress?: AnalysisProgress;
  created_at: string;
  notes: string;
  is_bowling_video: boolean;
  overall_score: number;
  overall_score_assessable?: boolean;
  summary: string;
  action_type: string;
  camera_view?: "side_on" | "rear" | "front_on" | "oblique" | "unknown";
  camera_view_confidence?: "high" | "medium" | "low";
  phases: Phase[];
  faults: Fault[];
  coaching_priorities?: CoachingPriority[];
  strengths: string[];
  tips: string[];
  pace_band: { label?: string; min_kmh?: number | null; max_kmh?: number | null; confidence?: string };
  injury_risk: { level?: string; mixed_action?: boolean | null; counter_rotation?: string; notes?: string; areas?: InjuryArea[] };
  steps?: Step[];
  video_path?: string;
  video_meta?: {
    fps?: number; duration?: number; width?: number; height?: number;
    quality?: { rating?: string; flags?: string[]; samples?: number; mean_luminance?: number | null; median_sharpness?: number | null; method?: string };
  };
  has_pose?: boolean;
  analysis_quality?: {
    score_confidence?: string; score_method?: string; assessable_steps?: number; step_coverage?: number;
    camera_view?: string; camera_view_confidence?: string;
    pose?: { rating?: string; frame_coverage?: number; critical_joint_coverage?: number; mean_joint_confidence?: number; interpolated_frames?: number; subject_selection_confidence?: string; competing_tracks?: number; joint_visibility?: Record<string, { observed_frames?: number; visible_frames?: number; coverage?: number; mean_confidence?: number }> };
    video?: { rating?: string; flags?: string[]; samples?: number; mean_luminance?: number | null; median_sharpness?: number | null; method?: string };
    event_methods?: Record<string, string>;
    joint_confidence?: Record<string, number | null>;
    contact_evidence?: Record<string, { observed_frames?: number; plateau_duration_s?: number }>;
    event_timing?: { overall?: "high" | "medium" | "low" | "unavailable"; events?: Record<string, "high" | "medium" | "low" | "unavailable"> };
    release_evidence?: { ball_separation_visible?: boolean; confidence?: string; notes?: string };
    limitations?: string[];
  };
};
export type Drill = {
  id: string; phase: string; title: string; duration: string; level: string;
  fault_tags: string[]; description: string; steps: string[]; recommended?: boolean;
};
export type Profile = { name: string; bowling_arm: string; bowling_style: string; level: string; age_band?: string };
export type Progress = {
  points: { id: string; date: string; score: number | null; pace: number; risk: string; faults: number }[];
  phase_avg: Record<string, number | null>;
  top_faults: { step_key: string; title: string; count: number; last_seen?: string; camera_view?: string }[];
  best_score: number; best_pace: number; total: number;
  step_trends?: {
    step_key: string; name: string; camera_view: string;
    current_analysis_id: string; previous_analysis_id: string;
    current_date: string; previous_date: string;
    current_score: number; previous_score: number; delta: number;
    direction: "improved" | "declined" | "stable";
  }[];
};
export type CoachMessage = { id: string; role: "user" | "assistant"; content: string; created_at: string };

let devicePromise: Promise<string> | null = null;
export function getDeviceId(): Promise<string> {
  if (!devicePromise) {
    devicePromise = (async () => {
      const existing = await storage.getItem<string | null>("device_id", null);
      if (existing) return existing;
      const id = `dev_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
      await storage.setItem("device_id", id);
      return id;
    })();
  }
  return devicePromise;
}

async function headers(json = false): Promise<Record<string, string>> {
  const h: Record<string, string> = { "X-Device-Id": await getDeviceId() };
  if (json) h["Content-Type"] = "application/json";
  return h;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export async function apiGet<T>(path: string): Promise<T> {
  return handle<T>(await fetch(`${API}${path}`, { headers: await headers() }));
}

export async function apiSend<T>(path: string, method: "POST" | "PUT" | "DELETE", body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(`${API}${path}`, { method, headers: await headers(true), body: body ? JSON.stringify(body) : undefined }),
  );
}

export async function uploadDelivery(
  file: { uri: string; name?: string; mimeType?: string },
  notes: string,
  onProgress?: (progress: AnalysisProgress) => void,
) {
  onProgress?.({ stage: "uploading", percent: 0, message: "Uploading your video" });
  const res = await uploadForm(`${API}/analyses`, {
    files: { video: { uri: file.uri, name: file.name || "delivery.mp4", mimeType: file.mimeType || "video/mp4" } },
    fields: { notes },
    headers: await headers(),
  });
  const { id } = await handle<{ id: string }>(res as unknown as Response);
  // Analysis runs on the server in the background; poll until it is ready (max ~6 min).
  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 3000));
    let a: Analysis & { status?: string; error?: string };
    try {
      a = await apiGet<Analysis & { status?: string; error?: string }>(`/analyses/${id}`);
    } catch (e: any) {
      if (/not found|404/i.test(String(e?.message))) throw new Error("This analysis is no longer available. Please upload the clip again.");
      continue; // brief network blip - keep waiting
    }
    if (a.progress) onProgress?.(a.progress);
    if (a.status === "failed") throw new Error(a.error || "Analysis failed. Please try a clearer, side-on clip.");
    if (a.status !== "processing") return a;
  }
  throw new Error("Analysis is taking longer than expected. Check your sessions shortly.");
}

export async function streamCoach(message: string, onDelta: (t: string) => void) {
  const init = { method: "POST", headers: await headers(true), body: JSON.stringify({ message }) };
  const doFetch: any = Platform.OS === "web" ? fetch : expoFetch;
  const res = await doFetch(`${API}/coach/chat`, init);
  if (!res.ok) throw new Error(`Coach unavailable (${res.status})`);
  const handleChunk = (raw: string) => {
    for (const line of raw.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (payload === "[DONE]") continue;
      const data = JSON.parse(payload);
      if (data.error) throw new Error(data.error);
      if (data.delta) onDelta(data.delta);
    }
  };
  const reader = res.body?.getReader?.();
  if (!reader) {
    handleChunk(await res.text());
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    parts.forEach(handleChunk);
  }
  if (buffer) handleChunk(buffer);
}

export const useAnalyses = () => useQuery({ queryKey: ["analyses"], queryFn: () => apiGet<Analysis[]>("/analyses") });
export const useAnalysis = (id: string) =>
  useQuery({ queryKey: ["analysis", id], queryFn: () => apiGet<Analysis>(`/analyses/${id}`), enabled: !!id });
export const useDrills = () => useQuery({ queryKey: ["drills"], queryFn: () => apiGet<Drill[]>("/drills") });
export const useProgress = () => useQuery({ queryKey: ["progress"], queryFn: () => apiGet<Progress>("/progress") });
export type WeeklyProgramme = {
  title: string;
  rationale: string;
  days: { day: string; type: "bowling" | "gym" | "skill" | "match" | "recovery" | "rest"; title: string; focus: string; details: string; intensity: string }[];
  constraints: { bowling_days: number; gym_days: number; skill_days: number; match_days: number; unavailable_days: string[]; notes: string };
  workload_at_generation: { status: "low" | "medium" | "high"; headline: string; acute: number };
  created_at: string;
};
export type WeeklyProgrammeResponse = { programme: WeeklyProgramme | null };
export const useWeeklyProgramme = () => useQuery({
  queryKey: ["coach-programme"],
  queryFn: () => apiGet<WeeklyProgrammeResponse>("/coach/programme"),
});

export const useDrillPracticeHistory = () => useQuery({ queryKey: ["coach-drill-history"], queryFn: () => apiGet<DrillPracticeHistory>("/coach/drills/history") });
export const useProfile = () => useQuery({ queryKey: ["profile"], queryFn: () => apiGet<Profile>("/profile") });

export type Step = {
  key: string; name: string; phase: string; description: string; ideal?: string; t: number | null; score: number;
  status: "good" | "ok" | "fault" | "not_visible"; observation: string; cue: string;
  coaching_classification?: "fault" | "opportunity" | "effective_variation" | "none";
  metrics: Record<string, number>;
  evidence_level?: "pose_estimate" | "visual_assessment" | "insufficient";
  timing_confidence?: "high" | "medium" | "low" | "unavailable";
  timing_method?: string;
};
export type PoseData = { width: number; height: number; frames: { t: number; k: number[][] | null; display_k?: number[][] | null }[] };
export type Ball = {
  n: number; created_at: string; is_bowling: boolean; score: number; pace_kmh?: number | null; hit_target?: boolean;
  good: string; fault: string; phase: string; observation: string; feedback: string; next_target: string; audio: string; block?: "bowling" | "test";
};
export type SessionActivityLog = {
  name: string; completed: boolean; actual_sets?: number | null; actual_reps?: string | null;
  effort?: "easy" | "moderate" | "hard" | null; notes?: string;
};
export type SessionCompletion = {
  activities: SessionActivityLog[];
  overall_feeling?: "fresh" | "normal" | "tired" | "rough" | null;
  notes?: string;
};
export type CoachSession = {
  id: string; created_at: string; focus: string; status: "active" | "ended"; intro: string; intro_audio: string;
  scheduled_session?: { day?: string; type?: "bowling" | "gym" | "skill" | "match" | "recovery" | "rest"; title?: string; focus?: string; details?: string; intensity?: string };
  balls: Ball[]; summary: string; summary_audio: string;
  plan?: SessionPlan;
  completion?: SessionCompletion;
  achievements?: { key: string; title: string; description: string }[];
  test_result?: { name?: string; balls?: number; hits?: number; avg_score?: number; top_pace?: number | null };
};
export type PlanItem = { name: string; minutes?: number; reps?: string; cue?: string };
export type SessionPlan = {
  session_mode?: "bowling" | "gym" | "recovery";
  pre_session?: PlanItem[]; warm_up?: PlanItem[]; drills?: PlanItem[]; activities?: PlanItem[]; cool_down?: PlanItem[]; tips?: string[];
  recovery?: { title?: string; items?: PlanItem[] };
  bowling?: { balls?: number; target?: string; rest_between_deliveries?: string }; test?: { name?: string; balls?: number; target?: string; description?: string };
};
export type InjuryArea = { key: string; level: string; score: number; drivers: string; prevention: string };
export type Workload = {
  acute: number; previous_week: number; chronic_weekly: number; acwr: number | null; rest_days_7: number; streak: number;
  weeks: { label: string; balls: number }[]; weekly_guide: number | null; flags: { level: string; text: string }[];
  status: "low" | "medium" | "high"; headline: string; advice: string; today: number;
  entries: { id: string; date: string; balls: number; intensity: number; source: string; note: string }[];
};
export const useWorkload = () => useQuery({ queryKey: ["workload"], queryFn: () => apiGet<Workload>("/workload") });

export function useDeviceId() {
  return useQuery({ queryKey: ["device-id"], queryFn: getDeviceId, staleTime: Infinity }).data;
}

export const mediaUrl = (analysisId: string, deviceId: string) => `${API}/media/${analysisId}?d=${encodeURIComponent(deviceId)}`;
export const ttsUrl = (key: string) => `${API}/tts/${key}.mp3`;

export const usePose = (id: string, enabled: boolean) =>
  useQuery({ queryKey: ["pose", id], queryFn: () => apiGet<PoseData>(`/analyses/${id}/pose`), enabled: !!id && enabled, staleTime: Infinity });

export const localDate = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export async function uploadBall(sessionId: string, file: { uri: string; name?: string; mimeType?: string }, block: "bowling" | "test" = "bowling") {
  const res = await uploadForm(`${API}/sessions/${sessionId}/balls`, {
    files: { video: { uri: file.uri, name: file.name || "ball.mp4", mimeType: file.mimeType || "video/mp4" } },
    fields: { block, day: localDate() },
    headers: await headers(),
  });
  return handle<Ball>(res as unknown as Response);
}
