import { useState } from "react";
import "./LeftSidebar.css";

interface FileItem {
  name: string;
  path: string;
}

interface OutlineItem {
  level: number;
  text: string;
}

interface Props {
  files: FileItem[];
  outline: OutlineItem[];
  onFileSelect: (path: string) => void;
  onCreateFile?: () => void;
  isOpen: boolean;
  onToggle: () => void;
}

export default function LeftSidebar({
  files,
  outline,
  onFileSelect,
  onCreateFile,
  isOpen,
  onToggle,
}: Props) {
  const [tab, setTab] = useState<"files" | "outline">("files");

  return (
    <div className={`left-sidebar ${isOpen ? "open" : ""}`}>
      {isOpen ? (
        <div className="left-panel">
          <div className="left-tabs">
            <button
              className={`left-tab ${tab === "files" ? "active" : ""}`}
              onClick={() => setTab("files")}
            >
              文件
            </button>
            <button
              className={`left-tab ${tab === "outline" ? "active" : ""}`}
              onClick={() => setTab("outline")}
            >
              大纲
            </button>
            <button
              className="left-close"
              onClick={onToggle}
              title="收起"
            >
              &times;
            </button>
          </div>
          <div className="left-body">
            {tab === "files" ? (
              <>
                {onCreateFile && (
                  <div className="file-header">
                    <span className="file-header-label">项目文件</span>
                    <button
                      className="file-new-btn"
                      onClick={onCreateFile}
                      title="新建 .md 文件"
                    >
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                        <path d="M6 1a.5.5 0 0 1 .5.5v4h4a.5.5 0 0 1 0 1h-4v4a.5.5 0 0 1-1 0v-4h-4a.5.5 0 0 1 0-1h4v-4A.5.5 0 0 1 6 1z" />
                      </svg>
                      新建
                    </button>
                  </div>
                )}
                {files.length > 0 ? (
                  <ul className="file-list">
                    {files.map((f) => (
                      <li
                        key={f.path}
                        className="file-item"
                        onClick={() => onFileSelect(f.path)}
                      >
                        {f.name}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="left-empty">
                    {onCreateFile ? '空文件夹 -- 点击上方"新建"创建笔记' : "打开文件夹以查看文件列表"}
                  </p>
                )}
              </>
            ) : outline.length > 0 ? (
              <ul className="outline-list">
                {outline.map((item, i) => (
                  <li
                    key={i}
                    className={`outline-item outline-h${item.level}`}
                  >
                    {item.text}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="left-empty">处理后自动生成大纲</p>
            )}
          </div>
        </div>
      ) : null}
      <button className="left-toggle" onClick={onToggle} title="侧边栏">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M2 3h12v1.5H2V3zm0 4h8v1.5H2V7zm0 4h10v1.5H2V11z" />
        </svg>
      </button>
    </div>
  );
}
