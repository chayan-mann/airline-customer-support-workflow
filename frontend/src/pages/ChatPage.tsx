import { useEffect, useState } from "react";
import { Avatar, Button, Card, Empty, Layout, Space, Typography } from "antd";
import { LogoutOutlined, UserOutlined } from "@ant-design/icons";
import { createChat, deleteChat, listChats, renameChat } from "../api";
import { useAuth } from "../auth/AuthContext";
import { ChatSidebar } from "../components/ChatSidebar";
import { ChatWindow } from "../components/ChatWindow";
import type { Chat } from "../types";

const { Header, Sider, Content } = Layout;
const { Title, Text } = Typography;

export function ChatPage() {
  const { user, logout } = useAuth();
  const [chats, setChats] = useState<Chat[]>([]);
  const [chatsLoading, setChatsLoading] = useState(true);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listChats()
      .then((result) => {
        setChats(result);
        if (result.length > 0) setActiveChatId(result[0].id);
      })
      .finally(() => setChatsLoading(false));
  }, []);

  async function handleNewChat() {
    setCreating(true);
    try {
      const chat = await createChat();
      setChats((prev) => [chat, ...prev]);
      setActiveChatId(chat.id);
    } finally {
      setCreating(false);
    }
  }

  async function handleRename(chatId: string, title: string) {
    const updated = await renameChat(chatId, title);
    setChats((prev) => prev.map((c) => (c.id === chatId ? updated : c)));
  }

  async function handleDelete(chatId: string) {
    await deleteChat(chatId);
    setChats((prev) => {
      const next = prev.filter((c) => c.id !== chatId);
      if (activeChatId === chatId) {
        setActiveChatId(next[0]?.id ?? null);
      }
      return next;
    });
  }

  // Called by ChatWindow when a message's response carries an auto-generated
  // title (the chat's first message), so the sidebar updates without a refetch.
  function handleChatTitled(chatId: string, title: string) {
    setChats((prev) => prev.map((c) => (c.id === chatId ? { ...c, title } : c)));
  }

  return (
    <Layout style={{ minHeight: "100vh", background: "#fff" }}>
      <Header
        style={{
          background: "#fff",
          borderBottom: "1px solid #f0f0f0",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 24px",
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          Airline Customer Support
        </Title>
        <Space>
          <Avatar icon={<UserOutlined />} size="small" />
          <Text type="secondary">{user?.email}</Text>
          <Button icon={<LogoutOutlined />} onClick={() => logout()}>
            Logout
          </Button>
        </Space>
      </Header>
      <Layout style={{ background: "#fff" }}>
        <Sider width={260} style={{ background: "#fff", borderRight: "1px solid #f0f0f0" }}>
          <ChatSidebar
            chats={chats}
            loading={chatsLoading}
            creating={creating}
            activeChatId={activeChatId}
            onSelect={setActiveChatId}
            onNewChat={handleNewChat}
            onRename={handleRename}
            onDelete={handleDelete}
          />
        </Sider>
        <Content
          style={{
            background: "#fff",
            padding: 24,
            display: "flex",
            justifyContent: "center",
          }}
        >
          {activeChatId ? (
            <Card
              style={{ width: "100%", maxWidth: 760, height: "calc(100vh - 128px)" }}
              styles={{ body: { height: "100%", padding: 0 } }}
            >
              <ChatWindow chatId={activeChatId} onChatTitled={handleChatTitled} />
            </Card>
          ) : (
            <div style={{ margin: "auto" }}>
              <Empty description="No chats yet">
                <Button type="primary" loading={creating} onClick={handleNewChat}>
                  Start a new chat
                </Button>
              </Empty>
            </div>
          )}
        </Content>
      </Layout>
    </Layout>
  );
}
