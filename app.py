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
    - 動画ページのytInitialPlayerResponseから字幕URLを抽出する確実な方法
    """
    data = request.json
    video_id = data.get("video_id", "").strip()

    if not video_id:
        return jsonify({"status": "error", "error": "動画IDが指定されていません。"}), 400

    try:
        import json as json_lib
        import re
        import xml.etree.ElementTree as ET
        import html as html_lib

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        # ① 動画ページを取得
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        resp = requests.get(video_url, headers=headers, timeout=20)
        if not resp.ok:
            return jsonify({"status": "error", "error": f"動画ページの取得に失敗しました (HTTP {resp.status_code})"}), 400

        # ② ytInitialPlayerResponseからキャプションデータを抽出
        match = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;', resp.text)
        if not match:
            return jsonify({"status": "error", "error": "動画データの解析に失敗しました。ページ構造が変更された可能性があります。"}), 400

        player_data = json_lib.loads(match.group(1))
        captions = player_data.get("captions", {})
        caption_tracks = captions.get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])

        if not caption_tracks:
            return jsonify({"status": "error", "error": "この動画には字幕が設定されていません。"}), 400

        # ③ 日本語・英語の字幕を優先して選択
        preferred_track = None
        for lang_prefix in ["ja", "en"]:
            for track in caption_tracks:
                if track.get("languageCode", "").startswith(lang_prefix):
                    preferred_track = track
                    break
            if preferred_track:
                break
        if not preferred_track:
            preferred_track = caption_tracks[0]  # どれもなければ最初のもの

        # ④ 字幕XMLを取得してテキスト抽出
        base_url = preferred_track.get("baseUrl", "")
        if not base_url:
            return jsonify({"status": "error", "error": "字幕URLが見つかりませんでした。"}), 400

        transcript_resp = requests.get(base_url, headers=headers, timeout=15)
        if not transcript_resp.ok:
            return jsonify({"status": "error", "error": "字幕データの取得に失敗しました。"}), 400

        root = ET.fromstring(transcript_resp.text)
        texts = []
        for elem in root.findall("text"):
            if elem.text:
                texts.append(html_lib.unescape(elem.text))

        if not texts:
            return jsonify({"status": "error", "error": "字幕の内容が空でした。"}), 400

        transcript_text = " ".join(texts)
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
