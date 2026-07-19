import { useEffect, useRef, useState } from "react";
import { Button, Input, Spin } from "antd";
import { SendOutlined } from "@ant-design/icons";
import { approve, getHistory, reject, sendMessage } from "../api";
import type { ChatMessage, ChatResponse, PendingToolCall } from "../types";
import { MessageBubble } from "./MessageBubble";
import { PendingToolCard } from "./PendingToolCard";

interface Props {
  chatId: string;
}

export function ChatWindow({ chatId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingToolCalls, setPendingToolCalls] = useState<PendingToolCall[] | null>(null);
  const [input, setInput] = useState("");
  const [historyLoading, setHistoryLoading] = useState(true);
  const [sending, setSending] = useState(false);
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
  }, [messages, pendingToolCalls]);

  function applyResponse(response: ChatResponse) {
    if (response.status === "ok") {
      setPendingToolCalls(null);
      if (response.reply) {
        setMessages((prev) => [...prev, { role: "agent", content: response.reply! }]);
      }
    } else {
      setPendingToolCalls(response.pending_tool_calls);
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      const response = await sendMessage(chatId, text);
      applyResponse(response);
    } finally {
      setSending(false);
    }
  }

  async function handleApprove() {
    setSending(true);
    try {
      applyResponse(await approve(chatId));
    } finally {
      setSending(false);
    }
  }

  async function handleReject() {
    setSending(true);
    try {
      applyResponse(await reject(chatId));
    } finally {
      setSending(false);
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
          disabled={!!pendingToolCalls}
          loading={sending}
        >
          Send
        </Button>
      </div>
    </div>
  );
}
