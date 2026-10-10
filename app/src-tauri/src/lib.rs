use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::Manager;
use serde::{Deserialize, Serialize};
use serde_json::json;

struct PythonBackend(pub Mutex<Option<Child>>);

const API_BASE: &str = "http://127.0.0.1:18231";

// -- Request/Response types --

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProcessPayload {
    text: String,
    mode: Option<String>,
    folder_path: Option<String>,
    file_id: Option<String>,
    file_path: Option<String>,
    previous_output: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct AuditPayload {
    text: String,
    output: String,
    folder_path: Option<String>,
    file_id: Option<String>,
    file_path: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct RefinePayload {
    previous_output: String,
    answers: Vec<AnswerPayload>,
    user_note: Option<String>,
}

#[derive(Deserialize)]
struct AnswerPayload {
    question_index: i32,
    user_input: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct QuestionResp {
    category: String,
    needs_input: bool,
    question: String,
    source_text: String,
    alert_type: String,
    severity: String,
    score: f64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ProcessResp {
    output: String,
    questions: Vec<QuestionResp>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AuditResp {
    questions: Vec<QuestionResp>,
}

// -- Helpers --

fn parse_questions(data: &serde_json::Value) -> Vec<QuestionResp> {
    data["questions"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|q| {
                    Some(QuestionResp {
                        category: q["category"].as_str()?.to_string(),
                        needs_input: q["needsInput"].as_bool()
                            .or_else(|| q["needs_input"].as_bool())?,
                        question: q["question"].as_str()?.to_string(),
                        source_text: q["sourceText"].as_str()
                            .or_else(|| q["source_text"].as_str())
                            .unwrap_or("")
                            .to_string(),
                        alert_type: q["alertType"].as_str()
                            .or_else(|| q["alert_type"].as_str())
                            .unwrap_or("")
                            .to_string(),
                        severity: q["severity"].as_str().unwrap_or("medium").to_string(),
                        score: q["score"].as_f64().unwrap_or(0.0),
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

fn build_client(timeout_secs: u64) -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(timeout_secs))
        .no_proxy()
        .build()
        .map_err(|e| format!("HTTP客户端创建失败: {}", e))
}

async fn retry_post(url: &str, body: &serde_json::Value, timeout_secs: u64) -> Result<reqwest::Response, String> {
    let client = build_client(timeout_secs)?;
    let mut last_err = String::new();
    for attempt in 0..3 {
        match client.post(url).json(body).send().await {
            Ok(resp) => return Ok(resp),
            Err(e) => {
                last_err = e.to_string();
                if attempt < 2 {
                    tokio::time::sleep(Duration::from_secs(1)).await;
                }
            }
        }
    }
    Err(format!("请求失败(重试3次): {}", last_err))
}

fn is_port_in_use(port: u16) -> bool {
    std::net::TcpStream::connect(("127.0.0.1", port)).is_ok()
}

fn wait_for_backend(max_wait_secs: u64) -> bool {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .no_proxy()
        .build();
    let client = match client {
        Ok(c) => c,
        Err(_) => return false,
    };
    let start = Instant::now();
    while start.elapsed().as_secs() < max_wait_secs {
        if client.get(format!("{}/docs", API_BASE)).send().is_ok() {
            println!("[TextReconstructor] Backend ready in {:.1}s", start.elapsed().as_secs_f64());
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

// -- Tauri commands --

#[tauri::command]
async fn api_process(payload: ProcessPayload) -> Result<ProcessResp, String> {
    let mut body = serde_json::json!({
        "text": payload.text,
        "mode": payload.mode.unwrap_or_else(|| "developer".to_string()),
    });
    if let Some(fp) = payload.folder_path { body["folder_path"] = json!(fp); }
    if let Some(fid) = payload.file_id { body["file_id"] = json!(fid); }
    if let Some(fp) = payload.file_path { body["file_path"] = json!(fp); }
    if let Some(po) = payload.previous_output { body["previous_output"] = json!(po); }

    let resp = retry_post(&format!("{}/api/process", API_BASE), &body, 90).await?;
    if !resp.status().is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("API 错误: {}", body));
    }
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("解析失败: {}", e))?;
    Ok(ProcessResp {
        output: data["output"].as_str().unwrap_or("").to_string(),
        questions: parse_questions(&data),
    })
}

#[tauri::command]
async fn api_audit(payload: AuditPayload) -> Result<AuditResp, String> {
    let body = serde_json::json!({
        "text": payload.text,
        "output": payload.output,
        "folder_path": payload.folder_path.unwrap_or_default(),
        "file_id": payload.file_id.unwrap_or_default(),
        "file_path": payload.file_path.unwrap_or_default(),
    });

    let resp = retry_post(&format!("{}/api/audit", API_BASE), &body, 120).await?;
    if !resp.status().is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("API 错误: {}", body));
    }
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("解析失败: {}", e))?;
    Ok(AuditResp {
        questions: parse_questions(&data),
    })
}

#[tauri::command]
async fn api_refine(payload: RefinePayload) -> Result<ProcessResp, String> {
    let answers: Vec<serde_json::Value> = payload.answers.iter().map(|a| {
        json!({"question_index": a.question_index, "user_input": a.user_input})
    }).collect();

    let body = serde_json::json!({
        "previous_output": payload.previous_output,
        "answers": answers,
        "user_note": payload.user_note.unwrap_or_default(),
    });

    let resp = retry_post(&format!("{}/api/refine", API_BASE), &body, 90).await?;
    if !resp.status().is_success() {
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("API 错误: {}", body));
    }
    let data: serde_json::Value = resp.json().await.map_err(|e| format!("解析失败: {}", e))?;
    Ok(ProcessResp {
        output: data["output"].as_str().unwrap_or("").to_string(),
        questions: parse_questions(&data),
    })
}

// -- State persistence commands (proxy to Python backend) --

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct SaveStatePayload {
    folder_path: String,
    file_path: String,
    output: String,
    questions: Vec<serde_json::Value>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct LoadStatesPayload {
    folder_path: String,
}

#[tauri::command]
async fn api_save_state(payload: SaveStatePayload) -> Result<serde_json::Value, String> {
    let body = serde_json::json!({
        "folder_path": payload.folder_path,
        "file_path": payload.file_path,
        "output": payload.output,
        "questions": payload.questions,
    });
    let resp = retry_post(&format!("{}/api/save-state", API_BASE), &body, 15).await
        .map_err(|e| format!("保存失败: {}", e))?;
    resp.json().await.map_err(|e| format!("解析失败: {}", e))
}

#[tauri::command]
async fn api_load_states(payload: LoadStatesPayload) -> Result<serde_json::Value, String> {
    let body = serde_json::json!({
        "folder_path": payload.folder_path,
    });
    let resp = retry_post(&format!("{}/api/load-states", API_BASE), &body, 15).await
        .map_err(|e| format!("加载失败: {}", e))?;
    resp.json().await.map_err(|e| format!("解析失败: {}", e))
}

// -- App setup --

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![api_process, api_audit, api_refine, api_save_state, api_load_states])
        .setup(|app| {
            if !cfg!(debug_assertions) {
                if is_port_in_use(18231) {
                    println!("[TextReconstructor] Port 18231 already in use, using existing backend");
                } else {
                    start_conda_backend(app);
                    if !wait_for_backend(30) {
                        eprintln!("[TextReconstructor] WARNING: Backend not ready after 30s");
                    }
                }
            } else {
                println!("[TextReconstructor] Dev mode: start backend manually");
                println!("  uvicorn text_reconstructor.api:app --host 0.0.0.0 --port 18231");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<PythonBackend>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn start_conda_backend(app: &tauri::App) {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/Users/mac".to_string());
    let conda_path = format!("{}/miniconda3/etc/profile.d/conda.sh", home);

    let script = format!(
        "source {} && conda activate deep_learning_env && uvicorn text_reconstructor.api:app --host 0.0.0.0 --port 18231",
        conda_path
    );

    match Command::new("bash")
        .arg("-c")
        .arg(&script)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
    {
        Ok(child) => {
            app.manage(PythonBackend(Mutex::new(Some(child))));
            println!("[TextReconstructor] Conda backend started, waiting for ready...");
        }
        Err(e) => {
            eprintln!("[TextReconstructor] Failed to start conda backend: {}", e);
        }
    }
}
