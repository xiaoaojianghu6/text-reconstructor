import { invoke } from "@tauri-apps/api/core";
import type { ProcessResponse, RefineResponse, AuditResponse } from "../types";

export async function processText(
  text: string,
  mode: "writer" | "developer",
  folderPath?: string,
  fileId?: string,
  filePath?: string,
  previousOutput?: string,
): Promise<ProcessResponse> {
  return invoke<ProcessResponse>("api_process", {
    payload: {
      text,
      mode,
      folderPath: folderPath || null,
      fileId: fileId || null,
      filePath: filePath || null,
      previousOutput: previousOutput || null,
    },
  });
}

export async function auditText(
  text: string,
  output: string,
  folderPath?: string,
  fileId?: string,
  filePath?: string,
): Promise<AuditResponse> {
  return invoke<AuditResponse>("api_audit", {
    payload: {
      text,
      output,
      folderPath: folderPath || null,
      fileId: fileId || null,
      filePath: filePath || null,
    },
  });
}

export async function refineText(
  previousOutput: string,
  answers: { question_index: number; user_input: string }[],
  userNote: string,
): Promise<RefineResponse> {
  return invoke<RefineResponse>("api_refine", {
    payload: {
      previousOutput,
      answers,
      userNote: userNote || null,
    },
  });
}
