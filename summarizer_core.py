# ============================================================
#  AI要約ツール - summarizer_core.py (Web/API共有コアロジック)
# ============================================================

import os
import re
import sys
import time
import json
import tempfile
import requests
from bs4 import BeautifulSoup
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi

# ---- ① 設定 ----
PROJECT_ID = "gemini-summarizer-501110"
LOCATION   = "us-central1"

# ---- ①-2 クラウドサーバー用：Google認証情報の自動復元処理 ----
if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
    try:
        cred_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        json_data = json.loads(cred_json)
        
        # 一時ファイルにJSONを保存
        temp_cred_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        json.dump(json_data, temp_cred_file)
        temp_cred_file.close()
        
        # 環境変数に一時ファイルのパスを設定
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_cred_file.name
        print("💡 GOOGLE_APPLICATION_CREDENTIALS_JSON から認証情報を正常に復元しました。")
    except Exception as e:
        print(f"⚠️ GOOGLE_APPLICATION_CREDENTIALS_JSON の復元中にエラーが発生しました: {e}")

# Google Cloudの認証情報を使用して初期化
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

# ---- ② YouTube動画IDを抽出する関数 ----
def extract_youtube_video_id(url: str) -> str:
    patterns = [
        r'(?:v=|\/embed\/|\/shorts\/|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""

# ---- ③ YouTube動画の音声字幕（トランスクリプト）を取得する ----
def get_youtube_transcript(url_or_id: str) -> str:
    # 引数がすでに11文字の動画IDである場合（例: juQatrnVsGE）
    if len(url_or_id) == 11 and "/" not in url_or_id and "=" not in url_or_id:
        video_id = url_or_id
    else:
        # URLから動画IDを抽出する
        video_id = ""
        # 通常のURL: youtube.com/watch?v=...
        if "v=" in url_or_id:
            video_id = url_or_id.split("v=")[1].split("&")[0]
        # 短縮URL: youtu.be/...
        elif "youtu.be/" in url_or_id:
            video_id = url_or_id.split("youtu.be/")[1].split("?")[0]
        # ショート動画: youtube.com/shorts/...
        elif "shorts/" in url_or_id:
            video_id = url_or_id.split("shorts/")[1].split("?")[0]

    if not video_id:
        raise ValueError("YouTubeの動画IDを検出できませんでした。URLを確認してください。")

    # 方法1: 標準の youtube-transcript-api を試す
    try:
        # クラスメソッドを直接呼び出して、日本語(ja)か英語(en)を一発で取得する
        data = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja', 'en'])
        text_list = [item['text'] for item in data]
        return " ".join(text_list)
        
    except Exception as primary_error:
        print(f"⚠️ youtube-transcript-api が失敗しました（IPブロックの可能性あり）: {primary_error}")
        print("🔄 yt-dlp を使用した代替取得を試みます...")
        
        # 方法2: IPブロック対策に強い yt-dlp をバックアップとして使用する
        import yt_dlp
        
        ydl_opts = {
            'writeautosub': True,       # 自動生成の字幕も許可
            'writesubtitles': True,     # 通常の字幕も許可
            'subtitleslangs': ['ja', 'en'], # 日本語か英語
            'skip_download': True,      # 動画自体はダウンロードしない
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                
                # 字幕データのURLを探して解析する
                subtitles = info.get('subtitles', {}) or {}
                automatic_captions = info.get('automatic_captions', {}) or {}
                
                # 日本語(ja)か英語(en)の字幕URLを取得
                sub_url = ""
                for lang in ['ja', 'en']:
                    if lang in subtitles:
                        sub_url = subtitles[lang][0]['url']
                        break
                    elif lang in automatic_captions:
                        # json形式の自動生成字幕を選ぶ
                        for sub_format in automatic_captions[lang]:
                            if sub_format.get('ext') == 'json3' or 'json' in sub_format.get('url', ''):
                                sub_url = sub_format['url']
                                break
                        if sub_url:
                            break
                        sub_url = automatic_captions[lang][0]['url']
                        break
                
                if not sub_url:
                    raise ValueError("動画内に日本語または英語の字幕ファイルが見つかりませんでした。")
                
                # 字幕データをダウンロードしてパースする
                response = requests.get(sub_url, timeout=10)
                if response.status_code != 200:
                    raise RuntimeError("字幕ファイルの取得に失敗しました。")
                
                # JSON形式（json3）のパース
                if 'json3' in sub_url or 'srv3' in sub_url or response.headers.get('Content-Type', '').startswith('application/json') or response.text.strip().startswith('{'):
                    import json
                    sub_data = response.json()
                    events = sub_data.get('events', [])
                    text_parts = []
                    for event in events:
                        segs = event.get('segs', [])
                        for seg in segs:
                            t = seg.get('utf8', '').strip()
                            if t:
                                text_parts.append(t)
                    return " ".join(text_parts)
                # XML形式の簡易パース (BeautifulSoupを使用)
                else:
                    soup = BeautifulSoup(response.text, 'xml')
                    text_parts = [p.get_text() for p in soup.find_all('p')]
                    if not text_parts:
                        text_parts = [text.get_text() for text in soup.find_all('text')]
                    return " ".join(text_parts)
                    
        except Exception as backup_error:
            raise RuntimeError(
                f"YouTubeの字幕を取得できませんでした。字幕機能が完全にオフになっているか、"
                f"またはアクセス制限が非常に厳しくなっています。\n"
                f"エラー詳細:\n- 標準API: {primary_error}\n- バックアップ: {backup_error}"
            )

# ---- ④ Webページから本文を抜き出す関数 ----
def extract_text_from_url(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
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

# ---- ⑤ 1つのパートを要約する基本関数 ----
def summarize_single_chunk(text: str, is_youtube: bool = False, length: str = "短く", custom_instruction: str = "") -> str:
    if is_youtube:
        prompt = f"""
以下のテキストはYouTube動画の音声から書き起こされた字幕です。
{custom_instruction}
この内容を日本語で{length}要約してください。重要なポイントを整理してください。

【要約対象のテキスト】
{text}
"""
    else:
        prompt = f"""
以下のテキストを日本語で{length}要約してください。
{custom_instruction}
重要なポイントを整理してください。

【要約対象のテキスト】
{text}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text

# ---- ⑦ 巨大なテキストを分割して要約するメイン関数 ----
def summarize_large_text(text: str, is_youtube: bool = False, length: str = "詳しく", progress_callback=None) -> str:
    # 1回あたりに送信する文字数（15,000文字で区切る）
    CHUNK_SIZE = 15000
    
    # 15,000文字以下の場合は、従来通り1発で要約する
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
            
        instruction = "これは全体のパートの一部です。この範囲内の重要な会話やトピックを箇条書きで簡潔に抜き出してください。"
        summary = summarize_single_chunk(chunk, is_youtube, length="短く", custom_instruction=instruction)
        intermediate_summaries.append(summary)
        
        # 1分間のリクエスト回数制限を確実に避けるため、4秒待つ
        time.sleep(4)
        
    if progress_callback:
        progress_callback("すべてのパートを統合して最終要約を作成中...")
        
    combined_summaries = "\n\n".join([f"--- パート {i+1} の内容 ---\n{s}" for i, s in enumerate(intermediate_summaries)])
    
    final_prompt = f"""
以下のテキストは、長い動画（または記事）の各パートの要約です。
これらをすべて確認した上で、全体を通して「どのような主張や流れだったのか」を分かりやすく体系的に整理した、最終的な要約を日本語で{length}作成してください。
箇条書きを効果的に使い、全体の結論や重要な教訓がはっきりと伝わるようにしてください。

【各パートの要約】
{combined_summaries}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=final_prompt
    )
    return response.text

# ---- ⑦ 外部から呼び出すメインのインターフェース ----
def run_summarizer(input_content: str, progress_callback=None) -> str:
    """
    入力内容（URL、YouTubeリンク、通常テキスト）を判定し、要約結果を返す
    """
    input_content = input_content.strip()
    is_url = input_content.startswith("http://") or input_content.startswith("https://")
    is_youtube = is_url and ("youtube.com" in input_content or "youtu.be" in input_content)

    if is_youtube:
        video_id = extract_youtube_video_id(input_content)
        if not video_id:
            raise ValueError("YouTubeの動画IDを抽出できませんでした。URLを確認してください。")
        if progress_callback:
            progress_callback("YouTubeの字幕を取得中...")
        text_content = get_youtube_transcript(video_id)
    elif is_url:
        if progress_callback:
            progress_callback("Webサイトから記事の本文を抽出中...")
        text_content = extract_text_from_url(input_content)
    else:
        text_content = input_content

    if not text_content:
        raise ValueError("要約するテキストが存在しません。")

    # 分割要約を実行
    result = summarize_large_text(text_content, is_youtube=is_youtube, length="詳しく", progress_callback=progress_callback)
    return result
