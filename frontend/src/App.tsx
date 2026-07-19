import { useState } from "react";
import { Card, Input, Layout, Space, Typography } from "antd";
import { ChatWindow } from "./components/ChatWindow";

const { Header, Content } = Layout;
const { Title, Text } = Typography;

function App() {
  const [sessionId, setSessionId] = useState("default");
  const [sessionInput, setSessionInput] = useState("default");

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
          <Text type="secondary">Session ID</Text>
          <Input
            value={sessionInput}
            style={{ width: 180 }}
            onChange={(e) => setSessionInput(e.target.value)}
            onPressEnter={() => setSessionId(sessionInput.trim() || "default")}
            onBlur={() => setSessionId(sessionInput.trim() || "default")}
          />
        </Space>
      </Header>
      <Content
        style={{
          background: "#fff",
          padding: 24,
          display: "flex",
          justifyContent: "center",
        }}
      >
        <Card
          style={{ width: "100%", maxWidth: 720, height: "calc(100vh - 128px)" }}
          styles={{ body: { height: "100%", padding: 0 } }}
        >
          <ChatWindow sessionId={sessionId} />
        </Card>
      </Content>
    </Layout>
  );
}

export default App;
