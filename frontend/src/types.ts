export interface PendingToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export interface ChatResponse {
  status: "ok" | "pending_approval";
  reply: string | null;
  pending_tool_calls: PendingToolCall[] | null;
}

export interface HistoryMessage {
  role: "user" | "agent";
  content: string;
}

export interface HistoryResponse {
  messages: HistoryMessage[];
  pending_tool_calls: PendingToolCall[] | null;
}

export interface ChatMessage {
  role: "user" | "agent";
  content: string;
}

export interface User {
  id: string;
  email: string;
}

export interface Chat {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
