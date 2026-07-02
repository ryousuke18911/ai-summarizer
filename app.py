# ============================================================
#  AI要約ツール - app.py (Flask)
# ============================================================

import os
from flask import Flask, render_template, request, jsonify
from summarizer_core import run_summarizer

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    data = request.json
    if not data or "content" not in data:
        return jsonify({"status": "error", "error": "内容が送られていません。"}), 400

    content = data["content"].strip()
    req_type = data.get("type", "text").strip()
    if not content:
        return jsonify({"status": "error", "error": "入力が空です。"}), 400

    def on_progress(msg):
        print(f"[PROGRESS] {msg}")

    try:
        result = run_summarizer(content, req_type=req_type, progress_callback=on_progress)
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=True)
