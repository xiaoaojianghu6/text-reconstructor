import "./Editor.css";

interface Props {
  value: string;
  onChange: (text: string) => void;
}

export default function Editor({ value, onChange }: Props) {
  const charCount = value.length;

  return (
    <div className="editor">
      <div className="editor-header">
        <span className="editor-label">输入</span>
        <span className="editor-count">{charCount} 字</span>
      </div>
      <textarea
        className="editor-textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="在此输入或粘贴文本..."
        spellCheck={false}
      />
    </div>
  );
}
