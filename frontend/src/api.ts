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
  if (res.status === 204) return undefined as T;
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

export function renameChat(chatId: string, title: string): Promise<Chat> {
  return request(`/chats/${encodeURIComponent(chatId)}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export function deleteChat(chatId: string): Promise<void> {
  return request(`/chats/${encodeURIComponent(chatId)}`, { method: "DELETE" });
}

export function getHistory(chatId: string): Promise<HistoryResponse> {
  return request(`/history/${encodeURIComponent(chatId)}`);
}

// /chat, /approve, /reject stream newline-delimited JSON: zero or more
// {"type": "status", "text": "..."} progress lines (one per graph step),
// then one {"type": "final", ...ChatResponse fields} line. onStatus fires
// for each status line as it arrives; the returned promise resolves with
// the final line once the stream ends.
async function streamRequest(
  path: string,
  body: unknown,
  onStatus: (text: string) => void,
): Promise<ChatResponse> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `POST ${path} failed: ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody?.detail) detail = errBody.detail;
    } catch {
      // response wasn't JSON; keep the default message
    }
    throw new ApiError(res.status, detail);
  }
  if (!res.body) throw new ApiError(res.status, "Empty response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: ChatResponse | null = null;

  function handleLine(line: string) {
    const trimmed = line.trim();
    if (!trimmed) return;
    const event = JSON.parse(trimmed);
    if (event.type === "status" && event.text) {
      onStatus(event.text);
    } else if (event.type === "final") {
      final = {
        status: event.status,
        reply: event.reply ?? null,
        pending_tool_calls: event.pending_tool_calls ?? null,
        chat_title: event.chat_title ?? null,
      };
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newlineIndex: number;
    while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
      handleLine(buffer.slice(0, newlineIndex));
      buffer = buffer.slice(newlineIndex + 1);
    }
  }
  if (buffer.trim()) handleLine(buffer);

  if (!final) throw new ApiError(500, "Stream ended without a final response");
  return final;
}

export function sendMessage(
  chatId: string,
  message: string,
  onStatus: (text: string) => void,
): Promise<ChatResponse> {
  return streamRequest("/chat", { chat_id: chatId, message }, onStatus);
}

export function approve(chatId: string, onStatus: (text: string) => void): Promise<ChatResponse> {
  return streamRequest("/approve", { chat_id: chatId }, onStatus);
}

export function reject(chatId: string, onStatus: (text: string) => void): Promise<ChatResponse> {
  return streamRequest("/reject", { chat_id: chatId }, onStatus);
}
