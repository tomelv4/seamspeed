import { useQuery } from "@tanstack/react-query";
import { fetch as expoFetch } from "expo/fetch";
import { Platform } from "react-native";

import { uploadForm } from "@/src/utils/upload";
import { storage } from "@/src/utils/storage";

export const API = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

export type Phase = { key: string; name: string; score: number; feedback: string };
export type Fault = { title: string; phase: string; severity: "low" | "medium" | "high"; description: string; fix: string };
export type Analysis = {
  id: string;
  created_at: string;
  notes: string;
  is_bowling_video: boolean;
  overall_score: number;
  summary: string;
  action_type: string;
  phases: Phase[];
  faults: Fault[];
  strengths: string[];
  tips: string[];
  pace_band: { label?: string; min_kmh?: number; max_kmh?: number; confidence?: string };
  injury_risk: { level?: string; mixed_action?: boolean; counter_rotation?: string; notes?: string };
};
export type Drill = {
  id: string; phase: string; title: string; duration: string; level: string;
  fault_tags: string[]; description: string; steps: string[]; recommended?: boolean;
};
export type Profile = { name: string; bowling_arm: string; bowling_style: string; level: string };
export type Progress = {
  points: { id: string; date: string; score: number; pace: number; risk: string; faults: number }[];
  phase_avg: Record<string, number>;
  top_faults: { title: string; count: number }[];
  best_score: number; best_pace: number; total: number;
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

export async function uploadDelivery(file: { uri: string; name?: string; mimeType?: string }, notes: string) {
  const res = await uploadForm(`${API}/analyses`, {
    files: { video: { uri: file.uri, name: file.name || "delivery.mp4", mimeType: file.mimeType || "video/mp4" } },
    fields: { notes },
    headers: await headers(),
  });
  return handle<Analysis>(res as unknown as Response);
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
export const useProfile = () => useQuery({ queryKey: ["profile"], queryFn: () => apiGet<Profile>("/profile") });
