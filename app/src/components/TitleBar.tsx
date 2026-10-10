import { getCurrentWindow } from "@tauri-apps/api/window";
import "./TitleBar.css";

const appWindow = getCurrentWindow();

interface Props {
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export default function TitleBar({ theme, onToggleTheme }: Props) {
  return (
    <div className="titlebar" data-tauri-drag-region>
      <span className="titlebar-title" data-tauri-drag-region>
        Text Reconstructor
      </span>
      <div className="titlebar-controls">
        <button
          className="theme-toggle"
          onClick={onToggleTheme}
          title={theme === "dark" ? "切换浅色主题" : "切换深色主题"}
          aria-label="Toggle theme"
        >
          {theme === "dark" ? (
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 1a1 1 0 0 1 1 1v1a1 1 0 0 1-2 0V2a1 1 0 0 1 1-1zM8 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm6.446-5.554a1 1 0 0 1-.708.293h-1a1 1 0 0 1 0-2h1a1 1 0 0 1 .708 1.707zM3.262 6.74a1 1 0 0 1-.708-.293l-.707-.707a1 1 0 0 1 1.414-1.414l.707.707A1 1 0 0 1 3.262 6.74zM14.707 13.293a1 1 0 0 1-1.414 1.414l-.707-.707a1 1 0 1 1 1.414-1.414l.707.707zM2.293 1.293a1 1 0 0 1 1.414 0l.707.707a1 1 0 0 1-1.414 1.414l-.707-.707a1 1 0 0 1 0-1.414zM8 13a1 1 0 0 1 1 1v1a1 1 0 0 1-2 0v-1a1 1 0 0 1 1-1zM3.262 9.26a1 1 0 1 1-1.414 1.414l-.707-.707a1 1 0 0 1 1.414-1.414l.707.707z" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path d="M6 1a1 1 0 0 0-.894.553C4.393 2.653 3 4.637 3 7a5 5 0 0 0 9.428 2.356 1 1 0 0 0-.553-1.47A5.98 5.98 0 0 1 8 3a5.98 5.98 0 0 1-1.47-.553A1 1 0 0 0 6 1z" />
            </svg>
          )}
        </button>
        <button
          className="titlebar-btn"
          onClick={() => appWindow.minimize()}
          aria-label="Minimize"
        >
          <svg width="12" height="12" viewBox="0 0 12 12">
            <rect y="5" width="12" height="1.5" fill="currentColor" />
          </svg>
        </button>
        <button
          className="titlebar-btn"
          onClick={() => appWindow.toggleMaximize()}
          aria-label="Maximize"
        >
          <svg width="12" height="12" viewBox="0 0 12 12">
            <rect
              x="1.5"
              y="1.5"
              width="9"
              height="9"
              stroke="currentColor"
              strokeWidth="1.5"
              fill="none"
            />
          </svg>
        </button>
        <button
          className="titlebar-btn titlebar-btn-close"
          onClick={() => appWindow.close()}
          aria-label="Close"
        >
          <svg width="12" height="12" viewBox="0 0 12 12">
            <line
              x1="1"
              y1="1"
              x2="11"
              y2="11"
              stroke="currentColor"
              strokeWidth="1.5"
            />
            <line
              x1="11"
              y1="1"
              x2="1"
              y2="11"
              stroke="currentColor"
              strokeWidth="1.5"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}
