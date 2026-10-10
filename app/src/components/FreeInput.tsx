import "./FreeInput.css";

interface Props {
  value: string;
  onChange: (value: string) => void;
}

export default function FreeInput({ value, onChange }: Props) {
  return (
    <div className="free-input">
      <p className="free-input-label">对输出有其他调整要求?</p>
      <textarea
        className="free-input-textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="例如: 第三段太啰嗦，精简一下 / 把数据标注那段移到前面..."
      />
    </div>
  );
}
