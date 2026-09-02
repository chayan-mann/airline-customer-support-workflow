import { Avatar, Typography } from "antd";
import { UserOutlined, RobotOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../types";

const { Text } = Typography;

// Agent replies are markdown (the LLM writes **bold**, numbered lists,
// etc.) so they need real rendering; user messages are plain typed text.
const markdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => (
    <p style={{ margin: "0 0 8px", lineHeight: 1.6 }}>{children}</p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul style={{ margin: "0 0 8px", paddingLeft: 20 }}>{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol style={{ margin: "0 0 8px", paddingLeft: 20 }}>{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li style={{ marginBottom: 4 }}>{children}</li>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong style={{ fontWeight: 600 }}>{children}</strong>
  ),
  code: ({ children }: { children?: React.ReactNode }) => (
    <code
      style={{
        background: "rgba(0,0,0,0.06)",
        borderRadius: 4,
        padding: "1px 5px",
        fontSize: "0.9em",
      }}
    >
      {children}
    </code>
  ),
};

export function MessageBubble({ role, content }: ChatMessage) {
  const isUser = role === "user";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: isUser ? "row-reverse" : "row",
        alignItems: "flex-start",
        gap: 8,
        marginBottom: 12,
      }}
    >
      <Avatar
        icon={isUser ? <UserOutlined /> : <RobotOutlined />}
        style={{
          backgroundColor: isUser ? "#1677ff" : "#f0f0f0",
          color: isUser ? "#fff" : "#595959",
          flexShrink: 0,
        }}
      />
      <div
        style={{
          maxWidth: "72%",
          padding: "8px 12px",
          borderRadius: 8,
          background: isUser ? "#f0f5ff" : "#fafafa",
          border: `1px solid ${isUser ? "#adc6ff" : "#f0f0f0"}`,
        }}
      >
        {isUser ? (
          <Text style={{ whiteSpace: "pre-wrap" }}>{content}</Text>
        ) : (
          <div style={{ fontSize: 14 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
