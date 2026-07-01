/* ============================================================
   AI Multi-Summarizer - main.js (Async UI Interaction)
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
    const inputContent = document.getElementById("input-content");
    const submitBtn = document.getElementById("submit-btn");
    const buttonText = submitBtn.querySelector(".button-text");
    const spinner = submitBtn.querySelector(".loading-spinner");
    
    const statusPanel = document.getElementById("status-panel");
    const statusMessage = document.getElementById("status-message");
    
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
                        // 履歴をクリックしたら、その結果を表示
                        resultPanel.classList.remove("hidden");
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

    // 要約ボタンクリック時の処理
    submitBtn.addEventListener("click", async () => {
        const text = inputContent.value.trim();
        if (!text) {
            alert("要約する内容（URLまたは文章）を入力してください。");
            return;
        }

        // URLがYouTubeのものか判定するヘルパー関数
        function getYoutubeId(url) {
            const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|shorts\/|watch\?v=|\&v=)([^#\&\?]*).*/;
            const match = url.match(regExp);
            return (match && match[2].length === 11) ? match[2] : null;
        }

        // ブラウザ側でYouTubeの timedtext API から直接字幕を取得する関数
        async function fetchYoutubeTranscript(videoId) {
            // 日本語(ja)、英語(en)、日本語自動生成(ja&kind=asr) の順に取得を試みる
            const urls = [
                `https://www.youtube.com/api/timedtext?v=${videoId}&lang=ja`,
                `https://www.youtube.com/api/timedtext?v=${videoId}&lang=en`,
                `https://www.youtube.com/api/timedtext?v=${videoId}&lang=ja&kind=asr`,
                `https://www.youtube.com/api/timedtext?v=${videoId}&lang=en&kind=asr`
            ];

            let response = null;
            for (const subUrl of urls) {
                try {
                    const res = await fetch(subUrl);
                    if (res.ok && res.status === 200) {
                        const text = await res.text();
                        if (text && text.includes('<text')) {
                            response = text;
                            break;
                        }
                    }
                } catch (e) {
                    console.warn("字幕取得試行エラー: ", e);
                }
            }

            if (!response) {
                throw new Error("動画から日本語または英語の字幕を取得できませんでした。字幕機能が完全にオフになっている可能性があります。");
            }

            // XMLをパースして字幕テキストを取り出す
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(response, "text/xml");
            const textElements = xmlDoc.getElementsByTagName("text");
            
            let transcriptText = "";
            for (let i = 0; i < textElements.length; i++) {
                // HTMLエンティティ（&amp;など）のデコード用
                const tempDiv = document.createElement("div");
                tempDiv.innerHTML = textElements[i].textContent;
                transcriptText += tempDiv.innerText + " ";
            }

            return transcriptText.trim();
        }

        // UIを「要約中」の状態に切り替える (文字やサイズは変えず、クリック不可にするだけ)
        submitBtn.disabled = true;
        
        // 右側の結果枠に「要約中」の進捗を美しく表示する
        resultContent.innerHTML = `
            <div class="embedded-loader">
                <div class="pulse-loader"></div>
                <span class="status-msg">URLまたはテキストを解析中...</span>
            </div>
        `;

        // 簡易的な進捗表示アニメーション（擬似進捗）
        let progressStep = 0;
        const progressMessages = [
            "データを取得しています...",
            "AIモデル（Gemini）を呼び出し中...",
            "要約結果をまとめています..."
        ];
        
        const progressInterval = setInterval(() => {
            if (progressStep < progressMessages.length) {
                const loader = resultContent.querySelector(".status-msg");
                if (loader) {
                    loader.innerText = progressMessages[progressStep];
                }
                progressStep++;
            }
        }, 3000);

        try {
            let requestPayload = { content: text, is_youtube: false };

            // もしYouTubeのURLなら、ブラウザ（ユーザーの回線）で直接字幕を取得する！
            const youtubeId = getYoutubeId(text);
            if (youtubeId) {
                const loader = resultContent.querySelector(".status-msg");
                if (loader) loader.innerText = "YouTubeの音声字幕を取得中...";
                
                try {
                    const transcript = await fetchYoutubeTranscript(youtubeId);
                    requestPayload.content = transcript;
                    requestPayload.is_youtube = true;
                } catch (ytErr) {
                    clearInterval(progressInterval);
                    alert("YouTube字幕取得エラー: " + ytErr.message);
                    resultContent.innerHTML = `<p class="placeholder-text">YouTube動画から字幕を取得できませんでした。</p>`;
                    return;
                }
            }

            const response = await fetch("/api/summarize", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(requestPayload)
            });

            clearInterval(progressInterval);
            const data = await response.json();

            if (data.status === "success") {
                // 成功：結果を表示
                resultContent.innerHTML = formatMarkdown(data.result);
                
                // 履歴を更新
                loadHistory();
                
                // 結果表示エリアまでスムーズスクロール
                resultPanel.scrollIntoView({ behavior: "smooth" });
            } else {
                // エラー発生
                alert("要約エラー: " + data.error);
                resultContent.innerHTML = `<p class="placeholder-text">エラーが発生しました。内容を確認して再試行してください。</p>`;
            }

        } catch (err) {
            clearInterval(progressInterval);
            alert("通信エラーが発生しました。");
            resultContent.innerHTML = `<p class="placeholder-text">通信エラーが発生しました。</p>`;
        } finally {
            // UIを元に戻す (クリックできるようにするだけ)
            submitBtn.disabled = false;
        }
    });

    // コピーボタンの処理
    copyBtn.addEventListener("click", () => {
        // HTMLタグを除去したプレーンテキストをコピー
        const textToCopy = resultContent.innerText;
        navigator.clipboard.writeText(textToCopy).then(() => {
            const originalText = copyBtn.innerText;
            copyBtn.innerText = "コピーしました！";
            setTimeout(() => {
                copyBtn.innerText = originalText;
            }, 2000);
        }).catch((err) => {
            alert("コピーに失敗しました。ブラウザの権限を確認してください。");
        });
    });

    // マークダウンの簡単なHTML変換関数 (リスト表示などをきれいにするため)
    function formatMarkdown(text) {
        if (!text) return "";
        let formatted = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // 見出しの変換 (### や ##)
        formatted = formatted.replace(/^###\s+(.*)$/gm, "<h3>$1</h3>");
        formatted = formatted.replace(/^##\s+(.*)$/gm, "<h2>$1</h2>");
        formatted = formatted.replace(/^#\s+(.*)$/gm, "<h1>$1</h1>");

        // 強調表示の変換 (**太字**)
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

        // 箇条書きの変換 (* または -)
        formatted = formatted.replace(/^\s*[\*\-]\s+(.*)$/gm, "<li>$1</li>");
        
        // <li>タグの前後を <ul> で囲む処理
        formatted = formatted.replace(/(<li>.*<\/li>)/gs, "<ul>$1<\/ul>");
        
        // 改行を <br> に変換 (すでにタグ化されている箇所を除く)
        formatted = formatted.split("\n").map(line => {
            if (line.trim().startsWith("<h") || line.trim().startsWith("<u") || line.trim().startsWith("<l")) {
                return line;
            }
            return line + "<br>";
        }).join("\n");

        return formatted;
    }
});
