# ============================================================
#  AI要約ツール - summarizer.py (無限長・分割要約対応版)
# ============================================================

import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup

# ---- ① ライブラリのインポート確認 ----
try:
    from google import genai
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("❌ ライブラリが足りません。以下を実行してください：")
    print("   pip install google-genai beautifulsoup4 requests youtube-transcript-api")
    sys.exit(1)

# ---- ② 設定 ----
PROJECT_ID = "gemini-summarizer-501110"
LOCATION   = "us-central1"

client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

# ---- ③ YouTube動画IDをURLから抽出する関数 ----
def extract_youtube_video_id(url: str) -> str:
    patterns = [
        r'(?:v=|\/embed\/|\/shorts\/|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""

# ---- ④ YouTubeの字幕を取得する関数 ----
def get_youtube_transcript(video_id: str) -> str:
    try:
        # インスタンスを作成して字幕リストを取得
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        transcript = transcript_list.find_transcript(['ja', 'en'])
        data = transcript.fetch()
        
        # 字幕を一つの文章に結合
        text = " ".join([item.text for item in data])
        return text
    except Exception as e:
        raise ValueError(
            f"YouTubeの字幕を取得できませんでした。\n"
            f"※ 字幕機能が完全にオフになっている動画や、音楽のみの動画は要約できません。\n"
            f"エラー詳細: {e}"
        )

# ---- ⑤ Webページから本文を抜き出す関数 ----
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
            raise ValueError("ウェブページからテキストを抽出できませんでした")
        return article_text
    except Exception as e:
        print(f"❌ Webページの取得に失敗しました: {e}")
        sys.exit(1)

# ---- ⑥ 1つのパートを要約する基本関数 ----
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

# ---- ⑦ 巨大なテキストを分割して要約する高度な関数 ----
def summarize_large_text(text: str, is_youtube: bool = False, length: str = "詳しく") -> str:
    # 1回あたりに送信する文字数（12,000文字で区切る）
    CHUNK_SIZE = 12000
    
    # 12,000文字以下の場合は、従来通り1発で要約する
    if len(text) <= CHUNK_SIZE:
        return summarize_single_chunk(text, is_youtube, length)
        
    print(f"🔄 テキストが長いため（計 {len(text)} 文字）、自動的に分割して要約を開始します...")
    
    # チャンク（塊）に分割
    chunks = [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    print(f"📦 全 {len(chunks)} パートに分割しました。順次要約します。")
    
    intermediate_summaries = []
    
    for idx, chunk in enumerate(chunks):
        print(f" ⏳ パート {idx+1}/{len(chunks)} を処理中... ({len(chunk)}文字)")
        
        # 各パートの重要なトピックを箇条書きでまとめてもらう
        instruction = "これは全体のパートの一部です。この範囲内の重要な会話やトピックを箇条書きで簡潔に抜き出してください。"
        summary = summarize_single_chunk(chunk, is_youtube, length="短く", custom_instruction=instruction)
        intermediate_summaries.append(summary)
        
        # APIの1分間あたりのリクエスト上限（RPM）を超えないように2秒待つ
        time.sleep(2)
        
    print("\n✨ すべてのパートの要約が完了しました。これらを統合して最終的な要約を作成します...")
    
    # 各パートの結果を合体
    combined_summaries = "\n\n".join([f"--- パート {i+1} の内容 ---\n{s}" for i, s in enumerate(intermediate_summaries)])
    
    final_prompt = f"""
以下のテキストは、長い動画（または記事）の各パートの重要な要約です。
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


# ---- ⑧ メイン処理 ----
def main():
    print("=" * 50)
    print("🤖  AIマルチ要約ツール（YouTube / Web / テキスト）")
    print("=" * 50)
    print()

    input_file = "input.txt"

    # もし input.txt が無ければ作成
    if not os.path.exists(input_file):
        with open(input_file, "w", encoding="utf-8") as f:
            f.write("ここに要約したい「文章」「WebサイトのURL」または「YouTubeのURL」を保存してください。")
        print(f"📄 新しく '{input_file}' を作成しました。")
        sys.exit(0)

    # ファイルを読み込む
    with open(input_file, "r", encoding="utf-8") as f:
        input_content = f.read().strip()

    if not input_content or "ここに要約したい" in input_content:
        print(f"⚠️  '{input_file}' に要約する内容が入っていません。")
        sys.exit(1)

    is_url = input_content.startswith("http://") or input_content.startswith("https://")
    is_youtube = is_url and ("youtube.com" in input_content or "youtu.be" in input_content)

    text_content = ""
    
    # 分岐処理
    if is_youtube:
        video_id = extract_youtube_video_id(input_content)
        if not video_id:
            print("❌ YouTubeの動画IDをURLから抽出できませんでした。URLを確認してください。")
            sys.exit(1)
        print(f"🎥 YouTube動画を検知しました (動画ID: {video_id})")
        print("⏳ 動画の音声字幕を取得しています...")
        try:
            text_content = get_youtube_transcript(video_id)
        except Exception as e:
            print(f"❌ {e}")
            sys.exit(1)
    elif is_url:
        print(f"🌐 WebサイトのURLを検知しました。内容を読み込んでいます...\nURL: {input_content}")
        text_content = extract_text_from_url(input_content)
    else:
        print("📄 直接入力されたテキストを読み込みました。")
        text_content = input_content

    # 読み込んだ全体の文字数
    print(f"📄 読み込み完了（全体で {len(text_content)} 文字）")
    print("-" * 40)
    # プレビュー
    print(text_content[:150] + "..." if len(text_content) > 150 else text_content)
    print("-" * 40)
    print()
    
    print("⏳ 要約を開始します...")
    print()

    try:
        # 分割・統合要約を実行（ここで自動で長さが判定されます）
        result = summarize_large_text(text_content, is_youtube=is_youtube, length="詳しく")
        
        print("✅ 最終要約結果：")
        print("=" * 40)
        print(result)
        print("=" * 40)
        
        # 結果をファイルに保存する
        output_file = "output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"\n💾 要約結果を '{output_file}' に保存しました！")

    except Exception as e:
        print(f"❌ 要約中にエラーが発生しました:\n{e}")
        sys.exit(1)

    print()
    print("🎉 すべての処理が完了しました！")


if __name__ == "__main__":
    main()
