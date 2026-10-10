export interface QuestionResponse {
  category: "ambiguity" | "missing_info" | "contradiction" | "logic_jump";
  needsInput: boolean;
  question: string;
  sourceText: string;
  alertType: string;
  severity: "high" | "medium";
  score: number;
}

export interface ProcessResponse {
  output: string;
  questions: QuestionResponse[];
}

export interface AuditResponse {
  questions: QuestionResponse[];
}

export interface RefineResponse {
  output: string;
  questions: QuestionResponse[];
}

export interface FileState {
  output: string;
  questions: QuestionResponse[];
  auditLoading: boolean;
}
