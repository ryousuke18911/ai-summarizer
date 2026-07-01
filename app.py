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

@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    """
    画面から送られてきた内容を要約するAPI
    """
    data = request.json
    if not data or "content" not in data:
        return jsonify({"error": "要約する内容が送られていません。"}), 400

    input_content = data["content"]
    
    # 進行状況を保存するシンプルな変数（ローカル環境用）
    current_status = "処理を開始しました..."
    
    def progress_update(status):
        nonlocal current_status
        current_status = status
        print(f"[PROGRESS] {status}")

    try:
        # 要約コアモジュールを実行
        result = run_summarizer(input_content, progress_callback=progress_update)
        
        # 履歴に追加
        history_item = {
            "input": input_content[:50] + "..." if len(input_content) > 50 else input_content,
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
    return jsonify(summarize_history[-5:]) # 直近の5件のみ返す

if __name__ == "__main__":
    # ポート8888番でサーバーを起動
    app.run(host="0.0.0.0", port=8888, debug=True)
