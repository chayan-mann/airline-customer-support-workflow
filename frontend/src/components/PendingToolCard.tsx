import { Button, Card, Space, Typography } from "antd";
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import type { PendingToolCall } from "../types";

const { Text } = Typography;

interface Props {
  toolCall: PendingToolCall;
  loading: boolean;
  onApprove: () => void;
  onReject: () => void;
}

export function PendingToolCard({ toolCall, loading, onApprove, onReject }: Props) {
  const argsText = Object.entries(toolCall.args)
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(", ");

  return (
    <Card
      size="small"
      style={{
        marginBottom: 12,
        background: "#fffbe6",
        borderColor: "#ffe58f",
      }}
    >
      <Text>
        The agent wants to call: <Text code>{`${toolCall.name}(${argsText})`}</Text>
      </Text>
      <div style={{ marginTop: 8 }}>
        <Space>
          <Button
            type="primary"
            icon={<CheckOutlined />}
            loading={loading}
            onClick={onApprove}
          >
            Approve
          </Button>
          <Button danger icon={<CloseOutlined />} loading={loading} onClick={onReject}>
            Reject
          </Button>
        </Space>
      </div>
    </Card>
  );
}
