# ============================================================
#  AI要約ツール - app.py (Flask Webサーバー)
# ============================================================

import os
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
    ブラウザからは直接YouTubeにアクセスできない(CORS)ため、サーバー経由で取得
    """
    data = request.json
    video_id = data.get("video_id", "").strip()

    if not video_id:
        return jsonify({"status": "error", "error": "動画IDが指定されていません。"}), 400

    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

        # 日本語 → 英語 の優先順位で字幕を取得
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=['ja', 'en', 'ja-JP', 'en-US']
        )
        transcript_text = " ".join([t['text'] for t in transcript_list])

        if not transcript_text.strip():
            return jsonify({"status": "error", "error": "字幕の内容が空です。"}), 400

        return jsonify({"status": "success", "transcript": transcript_text})

    except Exception as e:
        error_msg = str(e)
        if "TranscriptsDisabled" in error_msg or "disabled" in error_msg.lower():
            return jsonify({"status": "error", "error": "この動画では字幕機能が無効になっています。"}), 400
        elif "NoTranscriptFound" in error_msg or "Could not find" in error_msg:
            return jsonify({"status": "error", "error": "日本語・英語の字幕が見つかりませんでした。字幕付きの動画をお試しください。"}), 400
        else:
            return jsonify({"status": "error", "error": f"字幕の取得に失敗しました: {error_msg}"}), 500

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
