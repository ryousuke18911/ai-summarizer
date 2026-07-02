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
                "content": "あなたは日本語のテキスト要約 of 専門家です。与えられた内容を分かりやすく日本語で要約してください。"
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

# ---- ③ YouTube動画の字幕を抽出する関数 ----
def extract_youtube_transcript(video_id: str) -> str:
    """
    YouTube動画の字幕をサーバー側で取得する
    - 動画ページのytInitialPlayerResponseから字幕URLを抽出
    """
    import xml.etree.ElementTree as ET
    import html as html_lib

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    resp = requests.get(video_url, headers=headers, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"動画ページの取得に失敗しました (HTTP {resp.status_code})")

    # ytInitialPlayerResponseからキャプションデータを抽出
    match = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;', resp.text)
    if not match:
        raise RuntimeError("動画データの解析に失敗しました。字幕が有効な動画ではないか、YouTubeの仕様が変更された可能性があります。")

    import json as json_lib
    player_data = json_lib.loads(match.group(1))
    captions = player_data.get("captions", {})
    caption_tracks = captions.get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])

    if not caption_tracks:
        raise ValueError("この動画には字幕が設定されていません。字幕が有効な別の動画をお試しください。")

    # 日本語・英語の字幕を優先して選択
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

    base_url = preferred_track.get("baseUrl", "")
    if not base_url:
        raise ValueError("字幕URLが見つかりませんでした。")

    transcript_resp = requests.get(base_url, headers=headers, timeout=15)
    if not transcript_resp.ok:
        raise RuntimeError("字幕データの取得に失敗しました。")

    root = ET.fromstring(transcript_resp.text)
    texts = []
    for elem in root.findall("text"):
        if elem.text:
            texts.append(html_lib.unescape(elem.text))

    if not texts:
        raise ValueError("字幕の内容が空でした。")

    return " ".join(texts)

# ---- ④ 1つのチャンクを要約する関数 ----
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

# ---- ⑤ 巨大なテキストを分割して要約するメイン関数 ----
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

# ---- ⑥ 外部から呼び出すメインのインターフェース ----
def run_summarizer(input_content: str, progress_callback=None) -> str:
    """
    入力内容（URL、通常テキスト）を判定し、要約結果を返す
    """
    input_content = input_content.strip()
    is_url = input_content.startswith("http://") or input_content.startswith("https://")
    is_youtube = is_url and ("youtube.com" in input_content or "youtu.be" in input_content)

    if is_youtube:
        if progress_callback:
            progress_callback("YouTubeの字幕を取得中...")
        
        # URLから動画ID(11文字)を抽出
        video_id_match = re.search(r'(?:v=|\/|shorts\/)([0-9A-Za-z_-]{11})', input_content)
        if not video_id_match:
            raise ValueError("YouTubeのURLから動画IDを検出できませんでした。正しいURLを入力してください。")
        
        video_id = video_id_match.group(1)
        text_content = extract_youtube_transcript(video_id)
        
        result = summarize_large_text(text_content, is_youtube=True, length="詳しく", progress_callback=progress_callback)
        return result

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
