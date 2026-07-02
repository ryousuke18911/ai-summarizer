# ============================================================
#  AI要約ツール - summarizer_core.py
#  AI: Groq (llama-3.3-70b-versatile)
# ============================================================

import os
import time
import requests
from bs4 import BeautifulSoup

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"

def _get_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY が設定されていません。Renderの環境変数を確認してください。")
    return api_key

def _call_ai(prompt: str) -> str:
    """Groq APIを呼び出してテキスト生成"""
    response = requests.post(
        GROQ_API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_get_api_key()}",
        },
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "あなたは日本語のテキスト要約の専門家です。"},
                {"role": "user",   "content": prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 4096,
        },
        timeout=120
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def extract_text_from_url(url: str) -> str:
    """URLからWebページ本文を抽出"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "header", "footer", "nav", "aside", "form", "iframe"]):
        tag.decompose()

    lines = [el.get_text().strip() for el in soup.find_all(["h1", "h2", "h3", "h4", "p"]) if el.get_text().strip()]
    text = "\n".join(lines)
    if not text:
        raise ValueError("ページから本文を抽出できませんでした。")
    return text

def summarize(text: str, progress_callback=None) -> str:
    """テキストを要約する（長い場合は分割処理）"""
    CHUNK_SIZE = 12000

    if len(text) <= CHUNK_SIZE:
        if progress_callback:
            progress_callback("AIが要約を作成中...")
        return _call_ai(f"以下のテキストを日本語で詳しく要約してください。重要なポイントを箇条書きで整理してください。\n\n{text}")

    # 長文：分割して中間要約→最終要約
    chunks = [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    if progress_callback:
        progress_callback(f"{len(chunks)} パートに分割して要約中...")

    summaries = []
    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(f"パート {i+1}/{len(chunks)} を処理中...")
        s = _call_ai(f"以下は長い文章の一部です。この部分の重要な内容を箇条書きで簡潔に抜き出してください。\n\n{chunk}")
        summaries.append(s)
        if i < len(chunks) - 1:
            time.sleep(1)

    if progress_callback:
        progress_callback("全体の要約を作成中...")
    combined = "\n\n".join([f"【パート{i+1}】\n{s}" for i, s in enumerate(summaries)])
    return _call_ai(f"以下は長い文章を分割して要約したものです。全体を通して分かりやすく日本語でまとめてください。\n\n{combined}")

def run_summarizer(input_content: str, progress_callback=None) -> str:
    """メインの要約インターフェース"""
    input_content = input_content.strip()
    if not input_content:
        raise ValueError("入力が空です。")

    is_url = input_content.startswith("http://") or input_content.startswith("https://")

    if is_url:
        if progress_callback:
            progress_callback("Webページから本文を抽出中...")
        try:
            text = extract_text_from_url(input_content)
        except Exception as e:
            raise RuntimeError(f"Webページの取得に失敗しました: {e}")
    else:
        text = input_content

    return summarize(text, progress_callback=progress_callback)
