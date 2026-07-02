# ============================================================
#  AI要約ツール - app.py (Flask Webサーバー)
# ============================================================

import os
import requests
from flask import Flask, render_template, request, jsonify
from summarizer_core import run_summarizer


app = Flask(__name__)

# 要約履歴をメモリに一時保存（簡易版キャッシュ）
summarize_history = []

@app.route("/")
def index():
    """
    メインのウェブ画面を表示する
    """
    return render_template("index.html")

@app.route("/api/youtube-transcript", methods=["POST"])
def api_youtube_transcript():
    """
    YouTube動画の字幕をサーバー側で取得するAPI
    - summarizer_core.py の共通ロジックを呼び出す
    """
    data = request.json
    video_id = data.get("video_id", "").strip()

    if not video_id:
        return jsonify({"status": "error", "error": "動画IDが指定されていません。"}), 400

    try:
        from summarizer_core import extract_youtube_transcript
        transcript_text = extract_youtube_transcript(video_id)
        return jsonify({"status": "success", "transcript": transcript_text})

    except Exception as e:
        return jsonify({"status": "error", "error": f"字幕の取得に失敗しました: {str(e)}"}), 500

@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    """
    画面から送られてきた内容を要約するAPI
    """
    data = request.json
    if not data or "content" not in data:
        return jsonify({"error": "要約する内容が送られていません。"}), 400

    input_content = data["content"]
    is_youtube = data.get("is_youtube", False)

    def progress_update(status):
        print(f"[PROGRESS] {status}")

    try:
        # すでにブラウザ側でYouTube字幕が抽出されている場合
        if is_youtube:
            from summarizer_core import summarize_large_text
            result = summarize_large_text(input_content, is_youtube=True, length="詳しく", progress_callback=progress_update)
        else:
            # Web記事・長文テキストは従来のルート
            result = run_summarizer(input_content, progress_callback=progress_update)

        # 履歴に追加
        history_item = {
            "input": "🎥 YouTube動画" if is_youtube else (input_content[:50] + "..." if len(input_content) > 50 else input_content),
            "output": result
        }
        summarize_history.append(history_item)

        return jsonify({
            "status": "success",
            "result": result
        })

    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route("/api/history", methods=["GET"])
def api_history():
    """
    過去の要約履歴を返すAPI
    """
    return jsonify(summarize_history[-5:])  # 直近の5件のみ返す

if __name__ == "__main__":
    # ポート8888番でサーバーを起動
    app.run(host="0.0.0.0", port=8888, debug=True)
