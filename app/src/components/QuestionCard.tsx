import Markdown from "react-markdown";
import type { QuestionResponse } from "../types";
import "./QuestionCard.css";

interface Props {
  question: QuestionResponse;
  index: number;
  answer: string;
  onAnswerChange: (index: number, value: string) => void;
}

const CATEGORY_LABELS: Record<string, { label: string; color: string }> = {
  ambiguity: { label: "疑点", color: "warning" },
  missing_info: { label: "缺漏", color: "warning" },
  contradiction: { label: "矛盾", color: "danger" },
  logic_jump: { label: "跳跃", color: "warning" },
};

export default function QuestionCard({
  question,
  index,
  answer,
  onAnswerChange,
}: Props) {
  const cat = CATEGORY_LABELS[question.category] || {
    label: "问题",
    color: "warning",
  };

  return (
    <div className={`qcard qcard-border-${cat.color}`}>
      <div className="qcard-header">
        <span className={`qcard-badge qcard-badge-${cat.color}`}>
          {cat.label}
        </span>
        <span className="qcard-severity">
          {question.severity === "high" ? "高" : "中"}
        </span>
      </div>
      <div className="qcard-question">
        <Markdown>{question.question}</Markdown>
      </div>
      {question.needsInput ? (
        <input
          className="qcard-input"
          value={answer}
          onChange={(e) => onAnswerChange(index, e.target.value)}
          placeholder="输入补充说明..."
        />
      ) : null}
    </div>
  );
}
