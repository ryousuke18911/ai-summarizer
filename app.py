# ============================================================
#  AI要約ツール - app.py (Flask)
# ============================================================

import time
import uuid
import threading
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from summarizer_core import run_summarizer

load_dotenv()  # ローカル開発時に .env からGROQ_API_KEY等を読み込む（Render本番では環境変数を直接使用）

app = Flask(__name__)

# ジョブ管理（個人利用・単一ワーカー前提のシンプルなインメモリ実装）
jobs = {}
jobs_lock = threading.Lock()
JOB_TTL_SEC = 60 * 60  # 1時間経過した古いジョブは掃除する


def _cleanup_old_jobs():
    now = time.time()
    expired = [jid for jid, j in jobs.items() if now - j["created_at"] > JOB_TTL_SEC]
    for jid in expired:
        jobs.pop(jid, None)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    data = request.json
    if not data or "content" not in data:
        return jsonify({"status": "error", "error": "内容が送られていません。"}), 400

    content = data["content"].strip()
    is_url = content.startswith("http://") or content.startswith("https://")
    default_type = "url" if is_url else "text"
    req_type = data.get("type", default_type).strip()
    style = data.get("style", "detailed").strip()
    if style not in ("concise", "detailed"):
        style = "detailed"

    if not content:
        return jsonify({"status": "error", "error": "入力が空です。"}), 400

    job_id = uuid.uuid4().hex
    with jobs_lock:
        _cleanup_old_jobs()
        jobs[job_id] = {
            "status": "running",
            "progress": "開始しています...",
            "result": None,
            "error": None,
            "created_at": time.time(),
        }

    def worker():
        def on_progress(msg):
            print(f"[PROGRESS] {msg}")
            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]["progress"] = msg

        try:
            result = run_summarizer(content, req_type=req_type, style=style, progress_callback=on_progress)
            with jobs_lock:
                jobs[job_id]["status"] = "done"
                jobs[job_id]["result"] = result
        except Exception as e:
            print(f"[ERROR] {e}")
            with jobs_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = str(e)

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"status": "success", "job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"status": "error", "error": "指定されたジョブが見つかりません。"}), 404
        return jsonify({
            "status": job["status"],
            "progress": job["progress"],
            "result": job["result"],
            "error": job["error"],
        })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=True)
