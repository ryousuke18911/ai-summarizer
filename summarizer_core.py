# ============================================================
#  AI要約ツール - summarizer_core.py (Web/API共有コアロジック)
#  AI: Groq (LLaMA 3) - 無料・高速・シンプル
# ============================================================

import os
import re
import time
import requests
from bs4 import BeautifulSoup

# ---- ① Groq API設定 ----
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"  # 高品質・無料モデル

def _get_api_key() -> str:
    """環境変数からGroq APIキーを取得する"""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY 環境変数が設定されていません。\n"
            "Render の Environment 設定で GROQ_API_KEY を追加してください。"
        )
    return api_key

def _call_ai(prompt: str) -> str:
    """Groq REST APIを呼び出してテキストを生成する"""
    api_key = _get_api_key()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "あなたは日本語のテキスト要約の専門家です。与えられた内容を分かりやすく日本語で要約してください。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 8192,
    }
    response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]

# ---- ② Webページから本文を抜き出す関数 ----
def extract_text_from_url(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, "html.parser")

        for trash in soup(["script", "style", "header", "footer", "nav", "aside", "form", "iframe"]):
            trash.decompose()

        lines = []
        for element in soup.find_all(["h1", "h2", "h3", "h4", "p"]):
            text = element.get_text().strip()
            if text:
                lines.append(text)

        article_text = "\n".join(lines)
        if not article_text.strip():
            raise ValueError("ウェブページから要約可能なテキストを抽出できませんでした。")
        return article_text
    except Exception as e:
        raise RuntimeError(f"Webページの取得に失敗しました: {e}")

# ---- ③ 1つのチャンクを要約する関数 ----
def summarize_single_chunk(text: str, is_youtube: bool = False, length: str = "短く", custom_instruction: str = "") -> str:
    if is_youtube:
        prompt = f"""以下のテキストはYouTube動画の音声から書き起こされた字幕です。
{custom_instruction}
この内容を日本語で{length}要約してください。重要なポイントを整理してください。

【要約対象のテキスト】
{text}
"""
    else:
        prompt = f"""以下のテキストを日本語で{length}要約してください。
{custom_instruction}
重要なポイントを整理してください。

【要約対象のテキスト】
{text}
"""
    return _call_ai(prompt)

# ---- ④ 巨大なテキストを分割して要約するメイン関数 ----
def summarize_large_text(text: str, is_youtube: bool = False, length: str = "詳しく", progress_callback=None) -> str:
    CHUNK_SIZE = 15000

    if len(text) <= CHUNK_SIZE:
        if progress_callback:
            progress_callback("AIが直接要約を作成中...")
        return summarize_single_chunk(text, is_youtube, length)

    chunks = [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    total_chunks = len(chunks)

    if progress_callback:
        progress_callback(f"計 {len(text)} 文字を {total_chunks} パートに分割して要約中...")

    intermediate_summaries = []

    for idx, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(f"パート {idx+1}/{total_chunks} を処理中...")

        instruction = "これは全体の一部です。この範囲内の重要な内容を箇条書きで簡潔に抜き出してください。"
        summary = summarize_single_chunk(chunk, is_youtube, length="短く", custom_instruction=instruction)
        intermediate_summaries.append(summary)
        time.sleep(1)

    if progress_callback:
        progress_callback("すべてのパートを統合して最終要約を作成中...")

    combined_summaries = "\n\n".join([f"--- パート {i+1} ---\n{s}" for i, s in enumerate(intermediate_summaries)])

    final_prompt = f"""以下は長い文章の各パートの要約です。
全体を通して「どのような主張や流れだったのか」を分かりやすく日本語で{length}まとめてください。
箇条書きを効果的に使い、重要なポイントが伝わるようにしてください。

【各パートの要約】
{combined_summaries}
"""
    return _call_ai(final_prompt)

# ---- ⑤ 外部から呼び出すメインのインターフェース ----
def run_summarizer(input_content: str, progress_callback=None) -> str:
    """
    入力内容（URL、通常テキスト）を判定し、要約結果を返す
    ※ YouTubeはJS側で字幕取得済みのため、is_youtube=Trueで来る
    """
    input_content = input_content.strip()
    is_url = input_content.startswith("http://") or input_content.startswith("https://")
    is_youtube = is_url and ("youtube.com" in input_content or "youtu.be" in input_content)

    if is_youtube:
        raise ValueError(
            "YouTube動画はブラウザ側で字幕を取得する必要があります。"
            "ブラウザのJavaScriptが有効になっているか確認してください。"
        )
    elif is_url:
        if progress_callback:
            progress_callback("Webサイトから記事の本文を抽出中...")
        text_content = extract_text_from_url(input_content)
    else:
        text_content = input_content

    if not text_content:
        raise ValueError("要約するテキストが存在しません。")

    result = summarize_large_text(text_content, is_youtube=False, length="詳しく", progress_callback=progress_callback)
    return result
