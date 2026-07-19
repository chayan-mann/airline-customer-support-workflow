import { Button, List, Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { Chat } from "../types";

const { Text } = Typography;

interface Props {
  chats: Chat[];
  loading: boolean;
  creating: boolean;
  activeChatId: string | null;
  onSelect: (chatId: string) => void;
  onNewChat: () => void;
}

export function ChatSidebar({
  chats,
  loading,
  creating,
  activeChatId,
  onSelect,
  onNewChat,
}: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} block loading={creating} onClick={onNewChat}>
          New Chat
        </Button>
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        <List
          loading={loading}
          dataSource={chats}
          locale={{ emptyText: "No chats yet" }}
          renderItem={(chat) => (
            <List.Item
              onClick={() => onSelect(chat.id)}
              style={{
                cursor: "pointer",
                padding: "10px 16px",
                background: chat.id === activeChatId ? "#f0f5ff" : undefined,
              }}
            >
              <Text ellipsis style={{ width: "100%" }}>
                {chat.title}
              </Text>
            </List.Item>
          )}
        />
      </div>
    </div>
  );
}
