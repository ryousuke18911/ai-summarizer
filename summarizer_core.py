# ============================================================
#  AI要約ツール - summarizer_core.py
#  AI: Groq (llama-3.3-70b-versatile / whisper-large-v3-turbo)
# ============================================================

import os
import re
import time
import tempfile
import subprocess
import requests
from bs4 import BeautifulSoup

GROQ_API_URL       = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL         = "llama-3.3-70b-versatile"
GROQ_WHISPER_URL   = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"

# YouTube要約機能: 実装済みだが、RenderのサーバーIPがYouTube側から
# ブロックされ字幕・音声のどちらも取得できないため、現在は無効化している。
# ホスティング環境が変わる等で状況が変わった場合はTrueにすれば再度使える。
YOUTUBE_FEATURE_ENABLED  = False

CHUNK_SIZE               = 4000       # AIに一度に渡すテキストの文字数（無料枠のレート制限に収まるよう抑えめに設定）
AUDIO_CHUNK_SEC          = 20 * 60     # 音声を分割する長さ（20分）
MAX_YOUTUBE_DURATION_SEC = 4 * 60 * 60  # 対応する動画の長さの上限（4時間）
RATE_LIMIT_MAX_RETRIES   = 8           # レート制限時の最大リトライ回数
RATE_LIMIT_DEFAULT_WAIT  = 20          # レート制限のヘッダーが読めない場合の待機秒数

YOUTUBE_ID_PATTERNS = [r'(?:v=|/embed/|/shorts/|youtu\.be/)([a-zA-Z0-9_-]{11})']

BLOCKED_MESSAGE = (
    "YouTube側からのアクセスが現在ブロックされているため、字幕・音声のどちらも取得できませんでした。"
    "サーバーのIPアドレスが一時的に制限されている可能性があります。しばらく時間をおいてから再度お試しください。"
)


class YouTubeAccessBlockedError(RuntimeError):
    """YouTube側でアクセスがブロックされた（IP制限・bot判定など）ことを表す"""
    pass


def _get_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY が設定されていません。Renderの環境変数を確認してください。")
    return api_key


def _rate_limit_wait_seconds(response) -> float:
    """レスポンスヘッダーから、レート制限解除までの待機秒数を推定する"""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after) + 1
        except ValueError:
            pass
    for header in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        reset = response.headers.get(header)
        if reset:
            try:
                return float(reset.rstrip("s")) + 1
            except ValueError:
                pass
    return RATE_LIMIT_DEFAULT_WAIT


def _call_ai(prompt: str, max_tokens: int = 1200, progress_callback=None) -> str:
    """Groq APIを呼び出してテキスト生成。レート制限時は自動的に待機してリトライする"""
    for attempt in range(RATE_LIMIT_MAX_RETRIES):
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
                "max_tokens": max_tokens,
            },
            timeout=120
        )
        if response.status_code in (413, 429):
            wait = _rate_limit_wait_seconds(response)
            if progress_callback:
                progress_callback(f"AIの利用制限（無料枠）に達したため {int(wait)} 秒待機します...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    raise RuntimeError("AIの利用制限（無料枠）のため要約を完了できませんでした。しばらく時間をおいて再度お試しください。")


def _call_whisper(audio_path: str) -> str:
    """Groq Whisper APIで音声ファイルを文字起こし"""
    with open(audio_path, "rb") as f:
        response = requests.post(
            GROQ_WHISPER_URL,
            headers={"Authorization": f"Bearer {_get_api_key()}"},
            files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
            data={"model": GROQ_WHISPER_MODEL, "response_format": "text"},
            timeout=300,
        )
    if not response.ok:
        raise RuntimeError(f"音声の文字起こしに失敗しました（{response.status_code}）: {response.text[:200]}")
    return response.text.strip()


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


# ---------------------------------------------------------------
#  YouTube対応
# ---------------------------------------------------------------

def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def extract_youtube_video_id(url: str) -> str:
    for pattern in YOUTUBE_ID_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def _get_youtube_captions(video_id: str):
    """字幕（手動・自動生成問わず）を取得。字幕自体が存在しない場合はNoneを返す。
    ブロック系のエラーはそのまま呼び出し元に投げる。"""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        IpBlocked, RequestBlocked, PoTokenRequired, CouldNotRetrieveTranscript,
    )

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        try:
            transcript = transcript_list.find_transcript(["ja", "en"])
        except Exception:
            transcript = next(iter(transcript_list))
        data = transcript.fetch()
        return " ".join(item.text for item in data)
    except (IpBlocked, RequestBlocked, PoTokenRequired) as e:
        raise YouTubeAccessBlockedError(str(e)) from e
    except CouldNotRetrieveTranscript:
        return None
    except StopIteration:
        return None


def _download_youtube_audio(video_id: str, dest_path: str, progress_callback=None):
    """音声のみをダウンロードする。戻り値は (ダウンロードしたファイルパス, 動画の長さ秒)"""
    import yt_dlp
    import imageio_ffmpeg

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": dest_path + ".%(ext)s",
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "ffmpeg_location": ffmpeg_path,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration") or 0
            if duration and duration > MAX_YOUTUBE_DURATION_SEC:
                raise ValueError(
                    f"動画が長すぎます。{MAX_YOUTUBE_DURATION_SEC // 3600}時間以内の動画のみ対応しています。"
                )
            if progress_callback:
                mins = max(1, round(duration / 60)) if duration else None
                progress_callback(f"音声をダウンロード中...（約{mins}分の動画）" if mins else "音声をダウンロード中...")
            ydl.download([url])
            audio_path = ydl.prepare_filename(info)
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if any(k in msg for k in ["Sign in to confirm", "not a bot", "HTTP Error 403", "HTTP Error 429"]):
            raise YouTubeAccessBlockedError(msg) from e
        raise RuntimeError(f"YouTube動画の音声取得に失敗しました: {msg}") from e

    return audio_path, duration


def _split_and_transcribe(audio_path: str, progress_callback=None) -> str:
    """音声をチャンクに分割し、Groq Whisperで順番に文字起こしして結合する"""
    import imageio_ffmpeg
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    with tempfile.TemporaryDirectory() as tmpdir:
        segment_pattern = os.path.join(tmpdir, "chunk_%03d.mp3")
        cmd = [
            ffmpeg_path, "-y", "-i", audio_path,
            "-ac", "1", "-ar", "16000", "-b:a", "64k",
            "-f", "segment", "-segment_time", str(AUDIO_CHUNK_SEC),
            "-reset_timestamps", "1",
            segment_pattern,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"音声の分割処理に失敗しました: {result.stderr[-300:]}")

        chunk_files = sorted(f for f in os.listdir(tmpdir) if f.startswith("chunk_"))
        if not chunk_files:
            raise RuntimeError("音声の分割に失敗しました。")

        transcripts = []
        for i, fname in enumerate(chunk_files):
            if progress_callback:
                progress_callback(f"音声を文字起こし中...（{i + 1}/{len(chunk_files)}）")
            transcripts.append(_call_whisper(os.path.join(tmpdir, fname)))
        return " ".join(transcripts)


def get_youtube_transcript(video_id: str, progress_callback=None) -> str:
    """字幕を優先し、無ければ音声から文字起こしする"""
    if progress_callback:
        progress_callback("字幕を確認中...")

    caption_blocked = False
    try:
        captions = _get_youtube_captions(video_id)
        if captions:
            return captions
    except YouTubeAccessBlockedError:
        caption_blocked = True

    if progress_callback:
        progress_callback("字幕が見つからないため、音声から文字起こしします...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            dest_base = os.path.join(tmpdir, "audio")
            audio_path, _ = _download_youtube_audio(video_id, dest_base, progress_callback)
            return _split_and_transcribe(audio_path, progress_callback)
    except YouTubeAccessBlockedError:
        raise RuntimeError(BLOCKED_MESSAGE)
    except Exception as e:
        if caption_blocked:
            raise RuntimeError(BLOCKED_MESSAGE)
        raise RuntimeError(
            f"この動画は字幕がなく、音声からの文字起こしにも失敗しました。詳細: {e}"
        )


# ---------------------------------------------------------------
#  要約
# ---------------------------------------------------------------

STYLE_PROMPTS = {
    "concise":  "簡潔に（全体で5〜8個程度の箇条書きで、要点だけを）",
    "detailed": "詳しく（背景や具体例も含めて、箇条書きと補足説明で）",
}


def summarize(text: str, style: str = "detailed", is_youtube: bool = False, progress_callback=None) -> str:
    """テキストを要約する（長い場合は分割処理）"""
    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["detailed"])
    source_note = "以下はYouTube動画の音声から書き起こされたテキストです。" if is_youtube else "以下のテキストです。"

    if len(text) <= CHUNK_SIZE:
        if progress_callback:
            progress_callback("AIが要約を作成中...")
        return _call_ai(
            f"{source_note}この内容を日本語で{style_instruction}要約してください。\n\n{text}",
            max_tokens=2000,
            progress_callback=progress_callback,
        )

    # 長文：分割して中間要約→最終要約
    chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    if progress_callback:
        progress_callback(f"{len(chunks)} パートに分割して要約中...")

    summaries = []
    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(f"パート {i + 1}/{len(chunks)} を処理中...")
        s = _call_ai(
            f"{source_note}この範囲内の重要な内容を箇条書きで簡潔に抜き出してください。\n\n{chunk}",
            max_tokens=500,
            progress_callback=progress_callback,
        )
        summaries.append(s)
        if i < len(chunks) - 1:
            time.sleep(1)

    if progress_callback:
        progress_callback("全体の要約を作成中...")
    combined = "\n\n".join([f"【パート{i + 1}】\n{s}" for i, s in enumerate(summaries)])

    # 中間要約を統合した結果自体が長すぎる場合は、さらに再帰的に要約する（超長時間の動画・記事向け）
    if len(combined) > CHUNK_SIZE:
        return summarize(combined, style=style, is_youtube=False, progress_callback=progress_callback)

    return _call_ai(
        f"以下は長い文章を分割して要約したものです。全体を通して日本語で{style_instruction}まとめてください。\n\n{combined}",
        max_tokens=2000,
        progress_callback=progress_callback,
    )


def run_summarizer(input_content: str, req_type: str = "text", style: str = "detailed", progress_callback=None) -> str:
    """メインの要約インターフェース"""
    input_content = input_content.strip()
    if not input_content:
        raise ValueError("入力が空です。")

    is_url = input_content.startswith("http://") or input_content.startswith("https://")

    if req_type == "url":
        if not is_url:
            raise ValueError("URLの形式が正しくありません。http:// または https:// から始まるURLを入力してください。")

        if YOUTUBE_FEATURE_ENABLED and is_youtube_url(input_content):
            video_id = extract_youtube_video_id(input_content)
            if not video_id:
                raise ValueError("YouTubeの動画IDをURLから読み取れませんでした。URLを確認してください。")
            text = get_youtube_transcript(video_id, progress_callback=progress_callback)
            return summarize(text, style=style, is_youtube=True, progress_callback=progress_callback)

        if progress_callback:
            progress_callback("Webページから本文を抽出中...")
        try:
            text = extract_text_from_url(input_content)
        except Exception as e:
            raise RuntimeError(f"Webページの取得に失敗しました: {e}")
    else:  # "text"
        if is_url:
            raise ValueError("長文テキスト入力欄にURLが入力されています。URLは「Web記事URL」タブに入力してください。")
        text = input_content

    return summarize(text, style=style, progress_callback=progress_callback)
