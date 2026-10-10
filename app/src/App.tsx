import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import TitleBar from "./components/TitleBar";
import ModeSwitch from "./components/ModeSwitch";
import Editor from "./components/Editor";
import Output from "./components/Output";
import LeftSidebar from "./components/LeftSidebar";
import RightSidebar from "./components/RightSidebar";
import { processText, auditText, refineText } from "./hooks/useApi";
import {
  openSingleFile,
  openFolder,
  readTextFile,
  createFileInFolder,
  listFolder,
} from "./utils/fileOps";
import type { QuestionResponse, FileState } from "./types";
import type { FileEntry } from "./utils/fileOps";
import "./App.css";

function extractOutline(text: string) {
  return text
    .split("\n")
    .filter((l) => l.startsWith("##"))
    .map((l) => {
      const level = l.startsWith("###") ? 3 : 2;
      return { level, text: l.replace(/^#+\s*/, "") };
    });
}

function getInitialTheme(): "dark" | "light" {
  try {
    const stored = localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch {}
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function App() {
  const [theme, setTheme] = useState<"dark" | "light">(getInitialTheme);
  const [inputText, setInputText] = useState("");
  const [outputText, setOutputText] = useState("");
  const [mode, setMode] = useState<"writer" | "developer">("developer");
  const [questions, setQuestions] = useState<QuestionResponse[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [userNote, setUserNote] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);
  const [leftOpen, setLeftOpen] = useState(true);
  const [error, setError] = useState("");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [folderPath, setFolderPath] = useState("");
  const [currentFilePath, setCurrentFilePath] = useState("");

  // Per-file state cache (persisted to .text-reconstructor/*.state.json)
  const cacheRef = useRef<Record<string, FileState>>({});
  const inputRef = useRef(inputText);
  inputRef.current = inputText;
  const currentFilePathRef = useRef(currentFilePath);
  currentFilePathRef.current = currentFilePath;

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("theme", theme); } catch {}
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }, []);

  const outline = useMemo(() => extractOutline(outputText), [outputText]);

  // -- Disk persistence (via backend Python, not Tauri fs plugin) --

  async function persistState(fp: string, filePath: string, state: FileState) {
    try {
      const result = await invoke("api_save_state", {
        payload: {
          folderPath: fp,
          filePath,
          output: state.output,
          questions: state.questions,
        },
      });
      console.log("[persist] result:", result);
    } catch (e) {
      console.warn("[persist] FAILED:", e);
    }
  }

  async function loadDiskCache(fp: string): Promise<Record<string, FileState>> {
    try {
      const res = await invoke<{ states: Record<string, { output: string; questions: QuestionResponse[] }> }>(
        "api_load_states",
        { payload: { folderPath: fp } },
      );
      const result: Record<string, FileState> = {};
      for (const [path, data] of Object.entries(res.states)) {
        result[path] = {
          output: data.output || "",
          questions: data.questions || [],
          auditLoading: false,
        };
      }
      return result;
    } catch {
      return {};
    }
  }

  // -- File state cache helpers --

  const saveCurrentFileState = useCallback(() => {
    if (!currentFilePath) return;
    cacheRef.current[currentFilePath] = {
      output: outputText,
      questions,
      auditLoading,
    };
  }, [currentFilePath, outputText, questions, auditLoading]);

  const restoreFileState = useCallback((path: string) => {
    const state = cacheRef.current[path];
    if (state) {
      setOutputText(state.output);
      setQuestions(state.questions);
      setAuditLoading(state.auditLoading);
      if (state.questions.length > 0) setRightOpen(true);
    } else {
      setOutputText("");
      setQuestions([]);
      setAuditLoading(false);
    }
  }, []);

  // -- Handlers --

  async function handleOpenFile() {
    try {
      const result = await openSingleFile();
      if (result) {
        saveCurrentFileState();
        setInputText(result.content);
        setOutputText("");
        setQuestions([]);
        setCurrentFilePath("");
        setAuditLoading(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "打开文件失败");
    }
  }

  async function handleOpenFolder() {
    try {
      const result = await openFolder();
      if (result) {
        const loaded = await loadDiskCache(result.folderPath);
        cacheRef.current = loaded;
        setFiles(result.files);
        setFolderPath(result.folderPath);
        setLeftOpen(true);
        // 自动选中第一个文件（优先选有缓存状态的文件，其次第一个 .md/.txt 文件）
        const mdFiles = result.files.filter(f => !f.isDirectory);
        if (mdFiles.length > 0) {
          const cached = mdFiles.find(f => loaded[f.path]);
          const autoSelect = cached || mdFiles[0];
          handleFileSelect(autoSelect.path);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "打开文件夹失败");
    }
  }

  async function handleFileSelect(path: string) {
    if (path === currentFilePath) return;
    saveCurrentFileState();
    try {
      const content = await readTextFile(path);
      setInputText(content);
      setCurrentFilePath(path);
      restoreFileState(path);
      setAnswers({});
      setUserNote("");
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取文件失败");
    }
  }

  async function handleCreateFile() {
    if (!folderPath) return;
    try {
      const existingNames = new Set(files.map((f) => f.name));
      let n = 1;
      let name = `新笔记-${n}.md`;
      while (existingNames.has(name)) {
        n++;
        name = `新笔记-${n}.md`;
      }
      const filePath = await createFileInFolder(folderPath, name);
      const result = await listFolder(folderPath);
      setFiles(result.files);
      const content = await readTextFile(filePath);
      saveCurrentFileState();
      setInputText(content);
      setCurrentFilePath(filePath);
      setOutputText("");
      setQuestions([]);
      setAuditLoading(false);
      setAnswers({});
      setUserNote("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "新建文件失败");
    }
  }

  async function handleProcess() {
    if (!inputText.trim() || isProcessing) return;
    setIsProcessing(true);
    setError("");
    const inputSnapshot = inputRef.current;
    const previousOutput = outputText || undefined;

    try {
      const fileId = currentFilePath.split("/").pop() || "";
      const res = await processText(
        inputSnapshot,
        mode,
        folderPath || undefined,
        fileId || undefined,
        currentFilePath || undefined,
        previousOutput,
      );
      setOutputText(res.output);
      setQuestions(res.questions);
      setAnswers({});
      setUserNote("");
      if (res.questions.length > 0) setRightOpen(true);

      // Update cache + persist to disk
      if (currentFilePath) {
        const state: FileState = {
          output: res.output,
          questions: res.questions,
          auditLoading: !!folderPath,
        };
        cacheRef.current[currentFilePath] = state;
        if (folderPath) {
          console.log("[persist] saving:", currentFilePath, "output len:", res.output.length);
          persistState(folderPath, currentFilePath, state);
        } else {
          console.log("[persist] skipped: no folderPath");
        }
      } else {
        console.log("[persist] skipped: no currentFilePath");
      }

      // Kick off async audit (with 90s timeout)
      if (folderPath) {
        const auditPath = currentFilePath;
        const auditFileId = fileId;
        const capturedFolder = folderPath;

        const auditPromise = auditText(
          inputSnapshot,
          res.output,
          capturedFolder,
          auditFileId || undefined,
          auditPath || undefined,
        );

        // 90s 超时保护
        const timeoutPromise = new Promise<null>((resolve) =>
          setTimeout(() => resolve(null), 90000)
        );

        Promise.race([auditPromise, timeoutPromise])
          .then((auditRes) => {
            if (!auditRes) {
              // 超时
              if (auditPath === currentFilePathRef.current) {
                setAuditLoading(false);
                setError("管线审查超时(90s)，请稍后重试");
              }
              const existing = cacheRef.current[auditPath];
              if (existing) {
                cacheRef.current[auditPath] = { ...existing, auditLoading: false };
              }
              return;
            }
            const existing = cacheRef.current[auditPath];
            if (existing && existing.output === res.output) {
              const existingQs = existing.questions;
              const newQs = auditRes.questions.filter(
                nq => !existingQs.some(eq => eq.question === nq.question)
              );
              const merged = [...existingQs, ...newQs];
              const updated: FileState = {
                ...existing,
                questions: merged,
                auditLoading: false,
              };
              cacheRef.current[auditPath] = updated;
              if (auditPath === currentFilePathRef.current) {
                setQuestions(merged);
                setAuditLoading(false);
                if (merged.length > 0) setRightOpen(true);
              }
              persistState(capturedFolder, auditPath, updated);
            }
          })
          .catch((e) => {
            const existing = cacheRef.current[auditPath];
            if (existing) {
              const updated = { ...existing, auditLoading: false };
              cacheRef.current[auditPath] = updated;
              persistState(capturedFolder, auditPath, updated);
            }
            if (auditPath === currentFilePathRef.current) {
              setAuditLoading(false);
              const msg = typeof e === "string" ? e : e?.message || "管线审查失败";
              setError(msg);
            }
          });
        setAuditLoading(true);
      }
    } catch (e) {
      setError(typeof e === "string" ? e : e instanceof Error ? e.message : "处理失败");
    } finally {
      setIsProcessing(false);
    }
  }

  async function handleRefine() {
    if (!outputText || isProcessing) return;
    setIsProcessing(true);
    setError("");
    try {
      const answerList = Object.entries(answers)
        .filter(([, v]) => v.trim())
        .map(([i, v]) => ({
          question_index: Number(i),
          user_input: v,
        }));
      const res = await refineText(outputText, answerList, userNote);
      setOutputText(res.output);
      setQuestions(res.questions);
      setAnswers({});
      setUserNote("");

      // Update cache + persist
      if (currentFilePath) {
        const state: FileState = {
          output: res.output,
          questions: res.questions,
          auditLoading: false,
        };
        cacheRef.current[currentFilePath] = state;
        if (folderPath) {
          persistState(folderPath, currentFilePath, state);
        }
      }
    } catch (e) {
      setError(typeof e === "string" ? e : e instanceof Error ? e.message : "微调失败");
    } finally {
      setIsProcessing(false);
    }
  }

  function handleSendToInput() {
    setInputText(outputText);
    setOutputText("");
    setQuestions([]);
  }

  function handleAnswerChange(index: number, value: string) {
    setAnswers((prev) => ({ ...prev, [index]: value }));
  }

  return (
    <div className="app">
      <TitleBar theme={theme} onToggleTheme={toggleTheme} />
      <div className="toolbar">
        <div className="toolbar-left">
          <button className="toolbar-file-btn" onClick={handleOpenFile}>
            打开文件
          </button>
          <button className="toolbar-file-btn" onClick={handleOpenFolder}>
            打开文件夹
          </button>
          <ModeSwitch mode={mode} onChange={setMode} />
        </div>
        <div className="toolbar-right">
          {error && <span className="error-msg">{error}</span>}
          <button
            className="process-btn"
            onClick={handleProcess}
            disabled={isProcessing || !inputText.trim()}
          >
            {isProcessing ? "处理中..." : "处理"}
          </button>
        </div>
      </div>
      <div className="main-area">
        <LeftSidebar
          files={files}
          outline={outline}
          onFileSelect={handleFileSelect}
          onCreateFile={folderPath ? handleCreateFile : undefined}
          isOpen={leftOpen}
          onToggle={() => setLeftOpen(!leftOpen)}
        />
        <div className="panels">
          <div className="panel editor-panel">
            <Editor value={inputText} onChange={setInputText} />
          </div>
          <div className="divider" />
          <div className="panel output-panel">
            <Output value={outputText} onSendToInput={handleSendToInput} />
          </div>
        </div>
        <RightSidebar
          questions={questions}
          answers={answers}
          userNote={userNote}
          onAnswerChange={handleAnswerChange}
          onNoteChange={setUserNote}
          onRefine={handleRefine}
          isOpen={rightOpen}
          onToggle={() => setRightOpen(!rightOpen)}
          auditLoading={auditLoading}
        />
      </div>
    </div>
  );
}

export default App;
