import type { QuestionResponse } from "../types";
import QuestionCard from "./QuestionCard";
import FreeInput from "./FreeInput";
import "./RightSidebar.css";

interface Props {
  questions: QuestionResponse[];
  answers: Record<number, string>;
  userNote: string;
  onAnswerChange: (index: number, value: string) => void;
  onNoteChange: (note: string) => void;
  onRefine: () => void;
  isOpen: boolean;
  onToggle: () => void;
  auditLoading: boolean;
}

export default function RightSidebar({
  questions,
  answers,
  userNote,
  onAnswerChange,
  onNoteChange,
  onRefine,
  isOpen,
  onToggle,
  auditLoading,
}: Props) {
  return (
    <div className={`right-sidebar ${isOpen ? "open" : ""}`}>
      <button className="sidebar-toggle" onClick={onToggle} title="对抗机">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 1.5a5.5 5.5 0 110 11 5.5 5.5 0 010-11zM8 4a1 1 0 100 2 1 1 0 000-2zm0 3.5a.75.75 0 00-.75.75v3a.75.75 0 001.5 0v-3A.75.75 0 008 7.5z" />
        </svg>
      </button>
      {isOpen && (
        <div className="sidebar-panel">
          <div className="sidebar-header">
            <span className="sidebar-title">对抗机分析</span>
            <span className="sidebar-count">
              {questions.length} 个问题
            </span>
          </div>
          <div className="sidebar-body">
            {auditLoading && (
              <p className="audit-loading">管线审查中...</p>
            )}
            {!auditLoading && questions.length === 0 ? (
              <p className="no-questions">无待处理问题</p>
            ) : (
              questions.map((q, i) => (
                <QuestionCard
                  key={i}
                  question={q}
                  index={i}
                  answer={answers[i] || ""}
                  onAnswerChange={onAnswerChange}
                />
              ))
            )}
            <FreeInput value={userNote} onChange={onNoteChange} />
            {questions.length > 0 && (
              <div className="sidebar-actions">
                <button className="refine-btn" onClick={onRefine}>
                  微调输出
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
