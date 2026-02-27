const $ = (sel) => document.querySelector(sel);

const urlInput = $("#youtube-url");
const btnStart = $("#btn-start");
const btnStop = $("#btn-stop");
const statusEl = $("#status");
const transcriptList = $("#transcript-list");
const factcheckList = $("#factcheck-list");

let ws = null;
let activeUrl = "";  // 현재 실행 중인 URL (재연결 시 자동 재시작용)

const stats = { total: 0, checked: 0, fact: 0, partial: 0, false: 0, unverifiable: 0 };

const VERDICT_LABELS = {
    fact: "사실",
    partial: "부분사실",
    false: "거짓",
    unverifiable: "확인불가",
};

const SOURCE_TYPE_LABELS = {
    "reference": "REF",
    "web_search": "WEB",
    "llm": "LLM",
    "reference+web_search": "REF+WEB",
    "web_search+reference": "REF+WEB",
    "reference+llm": "REF+LLM",
    "web_search+llm": "WEB+LLM",
};

function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
}

function updateStats() {
    $("#stat-total").textContent = `전체: ${stats.total}`;
    $("#stat-checked").textContent = `검증: ${stats.checked}`;
    $("#stat-fact").textContent = `사실: ${stats.fact}`;
    $("#stat-partial").textContent = `부분: ${stats.partial}`;
    $("#stat-false").textContent = `거짓: ${stats.false}`;
    $("#stat-unknown").textContent = `확인불가: ${stats.unverifiable}`;
}

function addTranscript(data) {
    stats.total++;
    updateStats();

    const el = document.createElement("div");
    el.className = "transcript-item";
    el.id = `t-${data.id}`;
    el.innerHTML = `
        <div class="time">${formatTime(data.timestamp)}</div>
        <div>${data.text}</div>
    `;
    transcriptList.prepend(el);
}

function updateTranscriptStatus(statementId, needsCheck) {
    const el = document.getElementById(`t-${statementId}`);
    if (!el) return;
    el.classList.add(needsCheck ? "checking" : "skipped");
}

function addFactCheck(data) {
    stats.checked++;
    stats[data.verdict]++;
    updateStats();

    const el = document.createElement("div");
    el.className = `factcheck-card ${data.verdict}`;
    const srcLabel = SOURCE_TYPE_LABELS[data.source_type] || data.source_type || "WEB";
    el.innerHTML = `
        <div class="card-header">
            <span class="verdict-badge ${data.verdict}">${VERDICT_LABELS[data.verdict] || data.verdict}</span>
            <span class="source-badge">${srcLabel}</span>
        </div>
        <div class="statement">"${data.statement_text}"</div>
        <div class="explanation">${data.explanation}</div>
        <div class="confidence">신뢰도: ${Math.round(data.confidence * 100)}%</div>
    `;
    factcheckList.prepend(el);

    // Update transcript item
    const tEl = document.getElementById(`t-${data.statement_id}`);
    if (tEl) {
        tEl.classList.remove("checking");
        tEl.classList.add(data.verdict);
    }
}

function setStatus(text, className) {
    statusEl.textContent = text;
    statusEl.className = `status ${className || ""}`;
}

function connect() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        if (activeUrl) {
            // 재연결 시 자동으로 파이프라인 재시작
            ws.send(JSON.stringify({ action: "start", youtube_url: activeUrl }));
            setStatus("재연결 — 파이프라인 재시작 중...", "running");
        } else {
            setStatus("연결됨 — URL을 입력하고 시작하세요");
        }
        btnStart.disabled = false;
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
            case "transcription":
                addTranscript(msg.data);
                break;
            case "classification":
                updateTranscriptStatus(msg.data.statement_id, msg.data.needs_check);
                break;
            case "fact_check":
                addFactCheck(msg.data);
                break;
            case "status":
                if (msg.data.status === "running") {
                    setStatus("실시간 팩트체크 진행 중...", "running");
                    btnStart.disabled = true;
                    btnStop.disabled = false;
                } else if (msg.data.status === "stopped") {
                    setStatus(`중지됨 (처리된 청크: ${msg.data.chunks_processed || 0})`);
                    btnStart.disabled = false;
                    btnStop.disabled = true;
                }
                break;
            case "error":
                setStatus(`오류: ${msg.data.message}`, "error");
                break;
        }
    };

    ws.onclose = () => {
        setStatus("연결 끊김 — 재연결 중...");
        btnStart.disabled = true;
        btnStop.disabled = true;
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {
        setStatus("연결 오류", "error");
    };
}

btnStart.addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (!url) {
        setStatus("유튜브 URL을 입력하세요", "error");
        return;
    }
    if (ws && ws.readyState === WebSocket.OPEN) {
        activeUrl = url;
        ws.send(JSON.stringify({ action: "start", youtube_url: url }));
    }
});

btnStop.addEventListener("click", () => {
    activeUrl = "";
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "stop" }));
    }
});

// Load reference files display
async function loadRefFiles() {
    try {
        const res = await fetch("/api/reference-files");
        const data = await res.json();
        const container = $("#ref-files");
        if (data.files.length === 0) {
            container.innerHTML = '<span style="color:#555;font-size:0.78rem">참조 파일 없음 — data/facts/ 폴더에 파일을 추가하세요</span>';
            return;
        }

        const totalSize = data.files.reduce((acc, f) => {
            const num = parseFloat(f.size);
            return acc + (f.size.includes("MB") ? num : num / 1024);
        }, 0);

        // 폴더별 그룹핑
        const groups = {};
        data.files.forEach(f => {
            const parts = f.name.split("/");
            const folder = parts.length > 1 ? parts.slice(0, -1).join("/") : "";
            if (!groups[folder]) groups[folder] = [];
            groups[folder].push({ ...f, short: parts[parts.length - 1] });
        });

        const fileListHtml = Object.entries(groups).map(([folder, files]) => {
            const folderLabel = folder ? `<div class="ref-folder">${folder}/</div>` : "";
            const items = files.map(f =>
                `<div class="ref-file-item">
                    <span class="file-icon">${f.short.endsWith('.pdf') ? 'PDF' : f.short.endsWith('.hwp') || f.short.endsWith('.hwpx') ? 'HWP' : 'TXT'}</span>
                    <span class="file-name">${f.short}</span>
                    <span class="file-size">${f.size}</span>
                </div>`
            ).join("");
            return folderLabel + items;
        }).join("");

        container.innerHTML = `
            <div class="ref-summary" onclick="this.parentElement.classList.toggle('expanded')">
                <span>참조 문서 ${data.files.length}개 (${totalSize.toFixed(1)}MB)</span>
                <span class="ref-toggle">▼</span>
            </div>
            <div class="ref-file-list">${fileListHtml}</div>
        `;
    } catch (e) {
        console.error("Failed to load reference files:", e);
    }
}
loadRefFiles();

// Start connection
connect();
