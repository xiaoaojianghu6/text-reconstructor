import Markdown from "react-markdown";
import "./Output.css";

interface Props {
  value: string;
  onSendToInput: () => void;
}

export default function Output({ value, onSendToInput }: Props) {
  if (!value) {
    return (
      <div className="output output-empty">
        <p className="output-placeholder">处理结果将显示在这里</p>
      </div>
    );
  }

  return (
    <div className="output">
      <div className="output-header">
        <span className="output-label">输出</span>
        <button
          className="send-to-input-btn"
          onClick={onSendToInput}
          title="发送到输入面板"
        >
          &#8592; 输入
        </button>
      </div>
      <div className="output-content">
        <Markdown>{value}</Markdown>
      </div>
    </div>
  );
}
