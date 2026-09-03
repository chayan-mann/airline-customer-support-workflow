import type { ReactNode } from "react";
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

// Tool calls that are irreversible get a plainer, more alarming confirmation
// instead of the raw function-call text — everything else falls back to the
// generic rendering below.
function describeToolCall(toolCall: PendingToolCall): { content: ReactNode; danger: boolean } {
  if (toolCall.name === "cancel_booking" && typeof toolCall.args.confirmation_code === "string") {
    return {
      content: (
        <>
          The agent wants to cancel booking{" "}
          <Text strong>{toolCall.args.confirmation_code}</Text>. This can't be undone.
        </>
      ),
      danger: true,
    };
  }

  const argsText = Object.entries(toolCall.args)
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(", ");
  return {
    content: (
      <>
        The agent wants to call: <Text code>{`${toolCall.name}(${argsText})`}</Text>
      </>
    ),
    danger: false,
  };
}

export function PendingToolCard({ toolCall, loading, onApprove, onReject }: Props) {
  const { content, danger } = describeToolCall(toolCall);

  return (
    <Card
      size="small"
      style={{
        marginBottom: 12,
        background: danger ? "#fff1f0" : "#fffbe6",
        borderColor: danger ? "#ffa39e" : "#ffe58f",
      }}
    >
      <Text>{content}</Text>
      <div style={{ marginTop: 8 }}>
        <Space>
          <Button
            type="primary"
            danger={danger}
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
