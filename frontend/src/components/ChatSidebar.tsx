import { useState } from "react";
import { Button, Input, List, Popconfirm, Typography } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined } from "@ant-design/icons";
import type { Chat } from "../types";

const { Text } = Typography;

interface Props {
  chats: Chat[];
  loading: boolean;
  creating: boolean;
  activeChatId: string | null;
  onSelect: (chatId: string) => void;
  onNewChat: () => void;
  onRename: (chatId: string, title: string) => void;
  onDelete: (chatId: string) => void;
}

export function ChatSidebar({
  chats,
  loading,
  creating,
  activeChatId,
  onSelect,
  onNewChat,
  onRename,
  onDelete,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  function startEdit(chat: Chat) {
    setEditingId(chat.id);
    setEditValue(chat.title);
  }

  function commitEdit() {
    const title = editValue.trim();
    const id = editingId;
    setEditingId(null);
    if (id && title) onRename(id, title);
  }

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
              onClick={() => editingId !== chat.id && onSelect(chat.id)}
              onMouseEnter={() => setHoveredId(chat.id)}
              onMouseLeave={() => setHoveredId((id) => (id === chat.id ? null : id))}
              style={{
                cursor: "pointer",
                padding: "10px 16px",
                display: "flex",
                alignItems: "center",
                gap: 4,
                background: chat.id === activeChatId ? "#f0f5ff" : undefined,
              }}
            >
              {editingId === chat.id ? (
                <Input
                  size="small"
                  autoFocus
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  onPressEnter={commitEdit}
                  onBlur={commitEdit}
                  onKeyDown={(e) => e.key === "Escape" && setEditingId(null)}
                />
              ) : (
                <>
                  <Text ellipsis style={{ flex: 1 }}>
                    {chat.title}
                  </Text>
                  <div
                    style={{
                      display: "flex",
                      gap: 2,
                      visibility: hoveredId === chat.id ? "visible" : "hidden",
                    }}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        startEdit(chat);
                      }}
                    />
                    <Popconfirm
                      title="Delete this chat?"
                      description="This can't be undone."
                      okText="Delete"
                      okButtonProps={{ danger: true }}
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        onDelete(chat.id);
                      }}
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>
                  </div>
                </>
              )}
            </List.Item>
          )}
        />
      </div>
    </div>
  );
}
