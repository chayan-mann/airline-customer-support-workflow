import { useEffect, useRef, useState } from "react";
import { Avatar, Button, Input, Spin, Typography } from "antd";
import { RobotOutlined, SendOutlined } from "@ant-design/icons";
import { approve, getHistory, reject, sendMessage } from "../api";
import type { ChatMessage, ChatResponse, PendingToolCall } from "../types";
import { MessageBubble } from "./MessageBubble";
import { PendingToolCard } from "./PendingToolCard";

const { Text } = Typography;

interface Props {
  chatId: string;
  onChatTitled?: (chatId: string, title: string) => void;
}

export function ChatWindow({ chatId, onChatTitled }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingToolCalls, setPendingToolCalls] = useState<PendingToolCall[] | null>(null);
  const [input, setInput] = useState("");
  const [historyLoading, setHistoryLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    getHistory(chatId)
      .then((history) => {
        if (cancelled) return;
        setMessages(history.messages);
        setPendingToolCalls(history.pending_tool_calls);
      })
      .catch(() => {
        if (!cancelled) {
          setMessages([]);
          setPendingToolCalls(null);
        }
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [chatId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingToolCalls, statusText]);

  function applyResponse(response: ChatResponse) {
    if (response.status === "ok") {
      setPendingToolCalls(null);
      if (response.reply) {
        setMessages((prev) => [...prev, { role: "agent", content: response.reply! }]);
      }
    } else {
      setPendingToolCalls(response.pending_tool_calls);
    }
    // Set only on the chat's first message, when auto-titling succeeded.
    if (response.chat_title) {
      onChatTitled?.(chatId, response.chat_title);
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setSending(true);
    setStatusText("Thinking…");
    try {
      const response = await sendMessage(chatId, text, setStatusText);
      applyResponse(response);
    } finally {
      setSending(false);
      setStatusText(null);
    }
  }

  async function handleApprove() {
    setSending(true);
    setStatusText("Thinking…");
    try {
      applyResponse(await approve(chatId, setStatusText));
    } finally {
      setSending(false);
      setStatusText(null);
    }
  }

  async function handleReject() {
    setSending(true);
    setStatusText("Thinking…");
    try {
      applyResponse(await reject(chatId, setStatusText));
    } finally {
      setSending(false);
      setStatusText(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
        {historyLoading ? (
          <Spin />
        ) : (
          <>
            {messages.map((message, i) => (
              <MessageBubble key={i} role={message.role} content={message.content} />
            ))}
            {pendingToolCalls?.map((toolCall) => (
              <PendingToolCard
                key={toolCall.id}
                toolCall={toolCall}
                loading={sending}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            ))}
            {sending && statusText && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <Avatar
                  icon={<RobotOutlined />}
                  style={{ backgroundColor: "#f0f0f0", color: "#595959", flexShrink: 0 }}
                />
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px" }}>
                  <Spin size="small" />
                  <Text type="secondary" italic>
                    {statusText}
                  </Text>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </>
        )}
      </div>
      <div style={{ display: "flex", gap: 8, padding: 16, borderTop: "1px solid #f0f0f0" }}>
        <Input.TextArea
          value={input}
          autoSize={{ minRows: 1, maxRows: 4 }}
          placeholder="Ask about a booking, baggage, billing, or anything else..."
          disabled={!!pendingToolCalls || sending}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          disabled={!!pendingToolCalls || sending}
        >
          {sending ? "Sending…" : "Send"}
        </Button>
      </div>
    </div>
  );
}
