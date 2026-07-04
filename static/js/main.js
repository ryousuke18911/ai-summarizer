/* ============================================================
   AI要約ツール - main.js
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  // ---- Elements ----
  const tabs        = document.querySelectorAll(".tab");
  const panels      = document.querySelectorAll(".tab-panel");
  const urlInput    = document.getElementById("url-input");
  const textInput   = document.getElementById("text-input");
  const btn         = document.getElementById("summarize-btn");
  const btnText     = btn ? btn.querySelector(".btn-text") : null;
  const resultBody  = document.getElementById("result-body");
  const copyBtn     = document.getElementById("copy-btn");
  const downloadBtn = document.getElementById("download-btn");
  const charCount   = document.getElementById("char-count");
  const styleBtns   = document.querySelectorAll(".style-btn");
  const ytPreview   = document.getElementById("yt-preview");
  const ytThumb     = document.getElementById("yt-thumb");
  const ytTitle     = document.getElementById("yt-title");

  let currentTab   = "url";
  let currentStyle = "detailed";
  let lastResult   = "";
  let ytPreviewTimer = null;

  // ---- Tab switching ----
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      currentTab = tab.dataset.tab;
      tabs.forEach(t => t.classList.remove("active"));
      panels.forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      const panel = document.getElementById(`panel-${currentTab}`);
      if (panel) panel.classList.add("active");
    });
  });

  // ---- Style toggle ----
  styleBtns.forEach(sb => {
    sb.addEventListener("click", () => {
      currentStyle = sb.dataset.style;
      styleBtns.forEach(b => b.classList.remove("active"));
      sb.classList.add("active");
    });
  });

  // ---- Character counter (text mode) ----
  if (textInput && charCount) {
    textInput.addEventListener("input", () => {
      const len = textInput.value.length;
      charCount.textContent = len > 0 ? `${len.toLocaleString()} 文字` : "";
    });
  }

  // ---- YouTube URL detection & preview (oEmbed, no API key needed) ----
  function extractYoutubeId(url) {
    const m = url.match(/(?:v=|\/embed\/|\/shorts\/|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
    return m ? m[1] : null;
  }

  if (urlInput && ytPreview) {
    urlInput.addEventListener("input", () => {
      clearTimeout(ytPreviewTimer);
      const value = urlInput.value.trim();
      const videoId = extractYoutubeId(value);
      if (!videoId) {
        ytPreview.hidden = true;
        return;
      }
      ytPreviewTimer = setTimeout(() => showYoutubePreview(videoId), 300);
    });
  }

  async function showYoutubePreview(videoId) {
    try {
      const res = await fetch(
        `https://www.youtube.com/oembed?url=${encodeURIComponent("https://www.youtube.com/watch?v=" + videoId)}&format=json`
      );
      if (!res.ok) throw new Error("oembed failed");
      const data = await res.json();
      ytThumb.src = `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`;
      ytTitle.textContent = data.title || "";
      ytPreview.hidden = false;
    } catch (e) {
      ytPreview.hidden = true;
    }
  }

  // ---- Summarize (async job + polling) ----
  if (btn) {
    btn.addEventListener("click", async () => {
      const content = currentTab === "url"
        ? (urlInput ? urlInput.value.trim() : "")
        : (textInput ? textInput.value.trim() : "");

      if (!content) {
        showError(currentTab === "url" ? "URLを入力してください。" : "テキストを入力してください。");
        return;
      }
      if (currentTab === "url" && !content.startsWith("http")) {
        showError("正しいURLを入力してください（https:// から始まる形式）。");
        return;
      }
      if (currentTab === "text" && (content.startsWith("http://") || content.startsWith("https://"))) {
        showError("テキスト入力欄にURLが入力されています。URLの要約は「URL」タブを使用してください。");
        return;
      }

      setLoading(true, "開始しています...");

      try {
        const startRes = await fetch("/api/summarize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content, type: currentTab, style: currentStyle })
        });
        const startData = await startRes.json();

        if (startData.status !== "success" || !startData.job_id) {
          showError(startData.error || "処理を開始できませんでした。");
          setLoading(false);
          return;
        }

        await pollJob(startData.job_id);
      } catch (e) {
        showError("通信エラーが発生しました。しばらくしてから再試行してください。");
        setLoading(false);
      }
    });
  }

  function pollJob(jobId) {
    return new Promise((resolve) => {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`/api/status/${jobId}`);
          const data = await res.json();

          if (data.status === "running") {
            setLoading(true, data.progress || "処理中...");
          } else if (data.status === "done") {
            clearInterval(interval);
            showResult(data.result);
            setLoading(false);
            resolve();
          } else if (data.status === "error") {
            clearInterval(interval);
            showError(data.error || "不明なエラーが発生しました。");
            setLoading(false);
            resolve();
          }
        } catch (e) {
          clearInterval(interval);
          showError("通信エラーが発生しました。しばらくしてから再試行してください。");
          setLoading(false);
          resolve();
        }
      }, 1500);
    });
  }

  // ---- Copy ----
  if (copyBtn && resultBody) {
    copyBtn.addEventListener("click", () => {
      if (!lastResult) return;
      navigator.clipboard.writeText(lastResult).then(() => {
        copyBtn.textContent = "✓ コピー完了";
        setTimeout(() => { copyBtn.textContent = "コピー"; }, 2000);
      }).catch(() => {
        copyBtn.textContent = "コピーに失敗しました";
        setTimeout(() => { copyBtn.textContent = "コピー"; }, 2000);
      });
    });
  }

  // ---- Download ----
  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (!lastResult) return;
      const blob = new Blob([lastResult], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "要約結果.txt";
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  // ---- Helpers ----
  function setLoading(active, msg = "") {
    if (btn) btn.disabled = active;
    if (btnText) {
      btnText.textContent = active ? "要約中..." : "要約する";
    } else if (btn) {
      btn.textContent = active ? "要約中..." : "要約する";
    }
    if (active && resultBody) {
      resultBody.innerHTML = `
        <div class="loading-state">
          <div class="spinner"></div>
          <span class="loading-msg">${escapeHtml(msg)}</span>
        </div>`;
    }
  }

  function showResult(text) {
    lastResult = text || "";
    if (resultBody) {
      resultBody.innerHTML = `<div class="result-content">${formatMarkdown(text)}</div>`;
    }
  }

  function showError(msg) {
    lastResult = "";
    if (resultBody) {
      resultBody.innerHTML = `<div class="error-msg">❌ ${escapeHtml(msg)}</div>`;
    }
  }

  function escapeHtml(str) {
    return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }

  function formatMarkdown(text) {
    let t = escapeHtml(text);
    t = t.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
    t = t.replace(/^##\s+(.+)$/gm,  "<h2>$1</h2>");
    t = t.replace(/^#\s+(.+)$/gm,   "<h1>$1</h1>");
    t = t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/^\s*[-*]\s+(.+)$/gm, "<li>$1</li>");
    t = t.replace(/(<li>[\s\S]*?<\/li>)/g, "<ul>$1</ul>");
    t = t.split("\n").map(line => {
      if (/^<[hul]/.test(line.trim())) return line;
      return line + "<br>";
    }).join("\n");
    return t;
  }
});
