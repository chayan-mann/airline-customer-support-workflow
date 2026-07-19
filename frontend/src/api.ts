import type { Chat, ChatResponse, HistoryResponse, User } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: "include", // send/receive the httpOnly auth cookie cross-origin
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${init?.method ?? "GET"} ${path} failed: ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // response wasn't JSON; keep the default message
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export function register(email: string, password: string): Promise<User> {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<User> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<{ status: string }> {
  return request("/auth/logout", { method: "POST" });
}

export function getMe(): Promise<User> {
  return request("/auth/me");
}

export function listChats(): Promise<Chat[]> {
  return request("/chats");
}

export function createChat(title?: string): Promise<Chat> {
  return request("/chats", {
    method: "POST",
    body: JSON.stringify({ title: title ?? null }),
  });
}

export function getHistory(chatId: string): Promise<HistoryResponse> {
  return request(`/history/${encodeURIComponent(chatId)}`);
}

export function sendMessage(chatId: string, message: string): Promise<ChatResponse> {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify({ chat_id: chatId, message }),
  });
}

export function approve(chatId: string): Promise<ChatResponse> {
  return request("/approve", {
    method: "POST",
    body: JSON.stringify({ chat_id: chatId }),
  });
}

export function reject(chatId: string): Promise<ChatResponse> {
  return request("/reject", {
    method: "POST",
    body: JSON.stringify({ chat_id: chatId }),
  });
}
