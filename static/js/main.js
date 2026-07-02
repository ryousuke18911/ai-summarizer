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
  const charCount   = document.getElementById("char-count");

  let currentTab = "url";

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

  // ---- Character counter (text mode) ----
  if (textInput && charCount) {
    textInput.addEventListener("input", () => {
      const len = textInput.value.length;
      charCount.textContent = len > 0 ? `${len.toLocaleString()} 文字` : "";
    });
  }

  // ---- Summarize ----
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
        showError("テキスト入力欄にURLが入力されています。Web記事の要約は「Web記事URL」タブを使用してください。");
        return;
      }

      // Loading state
      setLoading(true, "解析中...");

      const messages = [
        "コンテンツを取得中...",
        "AIが要約を作成中...",
        "もうすぐ完了します..."
      ];
      let msgIdx = 0;
      const ticker = setInterval(() => {
        if (++msgIdx < messages.length) setLoading(true, messages[msgIdx]);
      }, 4000);

      try {
        const res = await fetch("/api/summarize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content, type: currentTab })
        });

        clearInterval(ticker);
        const data = await res.json();

        if (data.status === "success") {
          showResult(data.result);
        } else {
          showError(data.error || "不明なエラーが発生しました。");
        }
      } catch (e) {
        clearInterval(ticker);
        showError("通信エラーが発生しました。しばらくしてから再試行してください。");
      } finally {
        setLoading(false);
      }
    });
  }

  // ---- Copy ----
  if (copyBtn && resultBody) {
    copyBtn.addEventListener("click", () => {
      const text = resultBody.innerText;
      if (!text || resultBody.querySelector(".placeholder")) return;
      navigator.clipboard.writeText(text).then(() => {
        copyBtn.textContent = "✓ コピー完了";
        setTimeout(() => { copyBtn.textContent = "コピー"; }, 2000);
      });
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
          <span class="loading-msg">${msg}</span>
        </div>`;
    }
  }

  function showResult(text) {
    if (resultBody) {
      resultBody.innerHTML = `<div class="result-content">${formatMarkdown(text)}</div>`;
    }
  }

  function showError(msg) {
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
