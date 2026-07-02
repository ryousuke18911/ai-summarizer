/* ============================================================
   AI Multi-Summarizer - main.js (Async UI Interaction)
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
    const inputContent = document.getElementById("input-content");
    const submitBtn = document.getElementById("submit-btn");

    const resultPanel = document.getElementById("result-panel");
    const resultContent = document.getElementById("result-content");
    const copyBtn = document.getElementById("copy-btn");

    const historyList = document.getElementById("history-list");

    // 履歴を読み込む関数
    const loadHistory = async () => {
        try {
            const response = await fetch("/api/history");
            const history = await response.json();

            if (history.length > 0) {
                historyList.innerHTML = "";
                history.reverse().forEach((item) => {
                    const div = document.createElement("div");
                    div.className = "history-item";
                    div.innerText = item.input;
                    div.addEventListener("click", () => {
                        resultContent.innerHTML = formatMarkdown(item.output);
                        resultPanel.scrollIntoView({ behavior: "smooth" });
                    });
                    historyList.appendChild(div);
                });
            }
        } catch (err) {
            console.error("履歴の取得に失敗しました", err);
        }
    };

    // 初期起動時に履歴をロード
    loadHistory();

    // URLがYouTubeのものか判定するヘルパー関数
    function getYoutubeId(url) {
        const regExp = /^.*(youtu\.be\/|v\/|u\/\w\/|embed\/|shorts\/|watch\?v=|&v=)([^#&?]*).*/;
        const match = url.match(regExp);
        return (match && match[2].length === 11) ? match[2] : null;
    }

    // サーバー経由でYouTube字幕を取得する関数（CORSを回避）
    async function fetchYoutubeTranscriptFromServer(videoId) {
        const response = await fetch("/api/youtube-transcript", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ video_id: videoId })
        });
        const data = await response.json();
        if (data.status !== "success") {
            throw new Error(data.error || "字幕の取得に失敗しました。");
        }
        return data.transcript;
    }

    // 要約ボタンクリック時の処理
    submitBtn.addEventListener("click", async () => {
        const text = inputContent.value.trim();
        if (!text) {
            alert("要約する内容（URLまたは文章）を入力してください。");
            return;
        }

        // UIを「要約中」状態に切り替え
        submitBtn.disabled = true;
        resultContent.innerHTML = `
            <div class="embedded-loader">
                <div class="pulse-loader"></div>
                <span class="status-msg">URLまたはテキストを解析中...</span>
            </div>
        `;

        // 進捗表示アニメーション
        let progressStep = 0;
        const progressMessages = [
            "データを取得しています...",
            "AIモデルを呼び出し中...",
            "要約結果をまとめています..."
        ];

        const progressInterval = setInterval(() => {
            if (progressStep < progressMessages.length) {
                const loader = resultContent.querySelector(".status-msg");
                if (loader) loader.innerText = progressMessages[progressStep];
                progressStep++;
            }
        }, 3000);

        try {
            let requestPayload = { content: text, is_youtube: false };

            // YouTubeのURLなら、サーバー経由で字幕を取得
            const youtubeId = getYoutubeId(text);
            if (youtubeId) {
                const loader = resultContent.querySelector(".status-msg");
                if (loader) loader.innerText = "YouTubeの字幕をサーバーから取得中...";

                try {
                    const transcript = await fetchYoutubeTranscriptFromServer(youtubeId);
                    requestPayload.content = transcript;
                    requestPayload.is_youtube = true;
                } catch (ytErr) {
                    clearInterval(progressInterval);
                    submitBtn.disabled = false;
                    resultContent.innerHTML = `<p class="placeholder-text error-text">❌ YouTube字幕取得エラー: ${ytErr.message}</p>`;
                    return;
                }
            }

            // サーバーに要約リクエストを送信
            const loader2 = resultContent.querySelector(".status-msg");
            if (loader2) loader2.innerText = "AIが要約を作成中...";

            const response = await fetch("/api/summarize", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(requestPayload)
            });

            clearInterval(progressInterval);
            const data = await response.json();

            if (data.status === "success") {
                // 成功：結果を表示
                resultContent.innerHTML = formatMarkdown(data.result);
                loadHistory();
                resultPanel.scrollIntoView({ behavior: "smooth" });
            } else {
                // エラー発生
                resultContent.innerHTML = `<p class="placeholder-text error-text">❌ エラー: ${data.error}</p>`;
            }

        } catch (err) {
            clearInterval(progressInterval);
            resultContent.innerHTML = `<p class="placeholder-text error-text">❌ 通信エラーが発生しました。</p>`;
        } finally {
            submitBtn.disabled = false;
        }
    });

    // コピーボタンの処理
    copyBtn.addEventListener("click", () => {
        const textToCopy = resultContent.innerText;
        navigator.clipboard.writeText(textToCopy).then(() => {
            const originalText = copyBtn.innerText;
            copyBtn.innerText = "コピーしました！";
            setTimeout(() => { copyBtn.innerText = originalText; }, 2000);
        }).catch(() => {
            alert("コピーに失敗しました。ブラウザの権限を確認してください。");
        });
    });

    // マークダウンの簡単なHTML変換関数
    function formatMarkdown(text) {
        if (!text) return "";
        let formatted = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // 見出しの変換
        formatted = formatted.replace(/^###\s+(.*)$/gm, "<h3>$1</h3>");
        formatted = formatted.replace(/^##\s+(.*)$/gm, "<h2>$1</h2>");
        formatted = formatted.replace(/^#\s+(.*)$/gm, "<h1>$1</h1>");

        // 強調表示
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

        // 箇条書き
        formatted = formatted.replace(/^\s*[\*\-]\s+(.*)$/gm, "<li>$1</li>");
        formatted = formatted.replace(/(<li>.*<\/li>)/gs, "<ul>$1<\/ul>");

        // 改行
        formatted = formatted.split("\n").map(line => {
            if (line.trim().startsWith("<h") || line.trim().startsWith("<u") || line.trim().startsWith("<l")) {
                return line;
            }
            return line + "<br>";
        }).join("\n");

        return formatted;
    }
});
