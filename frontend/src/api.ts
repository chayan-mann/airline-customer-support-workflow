import type { ChatResponse, HistoryResponse } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function getHistory(sessionId: string): Promise<HistoryResponse> {
  return request(`/history/${encodeURIComponent(sessionId)}`);
}

export function sendMessage(sessionId: string, message: string): Promise<ChatResponse> {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

export function approve(sessionId: string): Promise<ChatResponse> {
  return request("/approve", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function reject(sessionId: string): Promise<ChatResponse> {
  return request("/reject", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}
