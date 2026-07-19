import { Avatar, Typography } from "antd";
import { UserOutlined, RobotOutlined } from "@ant-design/icons";
import type { ChatMessage } from "../types";

const { Text } = Typography;

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
        <Text style={{ whiteSpace: "pre-wrap" }}>{content}</Text>
      </div>
    </div>
  );
}
