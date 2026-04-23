#!/usr/bin/env python3
"""Download a video's captions and metadata via yt-dlp and produce a clean markdown transcript."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

YTDLP_SUFFIX_RE = re.compile(r"\s*\[[A-Za-z0-9_-]{11}\]\.[a-z]{2,5}$")
YTDLP_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]\.[a-z]{2,5}$")
SLUG_STRIP_RE = re.compile(r"[^a-z0-9\s]")
TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3} --> .+$")
TAG_RE = re.compile(r"<[^>]+>")
CUE_INDEX_RE = re.compile(r"^\d+$")
HEADER_RE = re.compile(r"^(WEBVTT|Kind:|Language:)")
SENTENCE_END_RE = re.compile(r'[.?!]["\']?$')
ARTIFACTS_RE = re.compile(r"^>>?\s*|&[a-z]+;|&#\d+;|\[[^\]]*\]")

LLM_CLEAN_PROMPT = """\
You are a transcript editor. The following is an auto-generated video transcript with transcription errors.

Your tasks:
1. Fix misspelled proper nouns, product names, and technical terms (e.g. "Ibuntu" → "Ubuntu").
2. Add paragraph breaks where the speaker shifts topic or pauses meaningfully.
3. Join short lines into flowing sentences where appropriate.
4. Do not rephrase, summarize, or add any content that isn't in the original.

Return only the corrected transcript text, no commentary.\
"""

LLM_SUMMARY_PROMPT = """\
You are a summarizer. The following is a cleaned video transcript.

Write a concise TL;DR summary (3-5 sentences) covering the main points and key takeaways.
Return only the summary, no commentary or heading.\
"""

_DOWNLOADS = Path.home() / "Downloads"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", _DOWNLOADS)).expanduser()
VTT_DIR = Path(os.environ.get("VTT_DIR", _DOWNLOADS)).expanduser()


def ensure_browser_ready(browser: str | None) -> None:
    if browser == "chrome" and sys.platform == "darwin":
        print("Opening Chrome with YouTube…")
        subprocess.run(["open", "-a", "Google Chrome", "https://www.youtube.com"], check=True)
        time.sleep(3)


def fetch_metadata(url: str, browser: str | None = None) -> dict:
    cmd = ["yt-dlp", "--dump-json", "--no-playlist"]
    if browser:
        cmd += ["--cookies-from-browser", browser]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def fetch_subtitles(url: str, output_dir: Path, lang: str, browser: str | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--skip-download",
        "--sub-lang", lang,
        "--sub-format", "vtt",
        "--output", str(output_dir / "%(title)s [%(id)s].%(ext)s"),
    ]
    if browser:
        cmd += ["--cookies-from-browser", browser]
    cmd.append(url)
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    vtt_files = list(output_dir.glob("*.vtt"))
    if not vtt_files:
        raise FileNotFoundError(f"No VTT subtitle file found after download (lang: {lang})")
    return vtt_files[0]


def clean_vtt(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if HEADER_RE.match(line) or TIMESTAMP_RE.match(line) or CUE_INDEX_RE.match(line):
            continue
        line = TAG_RE.sub("", line)
        line = ARTIFACTS_RE.sub("", line).strip()
        if line:
            text_lines.append(line)

    deduped = []
    prev = None
    for line in text_lines:
        if line != prev:
            deduped.append(line)
            prev = line
    return deduped


def join_sentences(lines: list[str]) -> str:
    paragraphs = []
    current = []
    for line in lines:
        current.append(line)
        if SENTENCE_END_RE.search(line):
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def _llm_client():
    from openai import OpenAI
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("LLM_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)
    return OpenAI(api_key=api_key, base_url=os.environ.get("LLM_BASE_URL"), timeout=120)


def _llm_call(client, model: str, system_prompt: str, text: str, label: str) -> str:
    print(f"{label}…")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
    )
    usage = response.usage
    print(f"Tokens — prompt: {usage.prompt_tokens:,}  completion: {usage.completion_tokens:,}  total: {usage.total_tokens:,}")
    return response.choices[0].message.content.strip()


def llm_clean(text: str, model: str) -> str:
    client = _llm_client()
    return _llm_call(client, model, LLM_CLEAN_PROMPT, text, f"Cleaning transcript with {model}")


def llm_summarize(cleaned: str, model: str) -> str:
    client = _llm_client()
    time.sleep(1)
    return _llm_call(client, model, LLM_SUMMARY_PROMPT, cleaned, f"Summarizing with {model}")


def slugify(title: str, words: int = 5) -> str:
    lowered = SLUG_STRIP_RE.sub("", title.lower())
    return "-".join(lowered.split()[:words])


def format_date(raw: str) -> str:
    if raw and len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def build_header(meta: dict) -> str:
    title = meta.get("title", "Untitled")
    channel = meta.get("channel") or meta.get("uploader", "Unknown")
    url = meta.get("webpage_url") or meta.get("original_url", "")
    date = format_date(meta.get("upload_date", ""))
    duration = meta.get("duration_string", "")
    description = (meta.get("description") or "").strip()

    lines = [f"# {title}", ""]
    if channel:
        lines.append(f"**Channel:** {channel}")
    if url:
        lines.append(f"**URL:** {url}")
    if date:
        lines.append(f"**Published:** {date}")
    if duration:
        lines.append(f"**Duration:** {duration}")

    if description:
        if len(description) > 1200:
            description = description[:1200].rsplit(" ", 1)[0] + "…"
        lines += ["", "---", "", description]

    lines += ["", "---", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Download captions from a URL (or process a local .vtt) into a clean markdown transcript.",
    )
    parser.add_argument("input", help="Video URL or local .vtt file")
    parser.add_argument("output", nargs="?", help="Output .md file (default: output/[title].md)")
    parser.add_argument("--join", action="store_true", help="Merge lines into sentence paragraphs (heuristic)")
    parser.add_argument("--llm", action="store_true", help="Clean transcript via LLM (fixes errors, adds paragraph breaks)")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "open-mistral-7b"),
                        help="LLM model to use (default: LLM_MODEL env var, or open-mistral-7b)")
    parser.add_argument("--lang", default="en", help="Subtitle language code (default: en)")
    parser.add_argument("--cookies-from-browser", metavar="BROWSER", dest="browser",
                        help="Pass cookies from this browser to yt-dlp (e.g. chrome, firefox)")
    args = parser.parse_args()

    input_arg = args.input
    is_url = input_arg.startswith("http://") or input_arg.startswith("https://")

    if is_url:
        ensure_browser_ready(args.browser)
        print("Fetching metadata…")
        try:
            meta = fetch_metadata(input_arg, browser=args.browser)
        except subprocess.CalledProcessError as e:
            print(f"yt-dlp metadata error:\n{e.stderr}", file=sys.stderr)
            sys.exit(1)

        title = meta.get("title", "transcript")
        video_id = meta.get("id", title)
        header = build_header(meta)

        print("Fetching subtitles…")
        try:
            vtt_path = fetch_subtitles(input_arg, VTT_DIR, args.lang, browser=args.browser)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Subtitle download error: {e}", file=sys.stderr)
            sys.exit(1)
        lines = clean_vtt(vtt_path)
    else:
        vtt_path = Path(input_arg)
        if not vtt_path.exists():
            print(f"File not found: {vtt_path}", file=sys.stderr)
            sys.exit(1)
        title = YTDLP_SUFFIX_RE.sub("", vtt_path.stem)
        m = YTDLP_ID_RE.search(vtt_path.name)
        video_id = m.group(1) if m else title
        header = f"# {title}\n\n"
        lines = clean_vtt(vtt_path)

    if args.llm:
        body = llm_clean("\n".join(lines), model=args.model)
        summary = llm_summarize(body, model=args.model)
        transcript = header + f"## TL;DR\n\n{summary}\n\n---\n\n" + body
    elif args.join:
        body = join_sentences(lines)
        transcript = header + body
    else:
        transcript = header + "\n".join(lines)

    if args.output:
        out = Path(args.output)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUTPUT_DIR / f"{slugify(title)}.md"

    out.write_text(transcript, encoding="utf-8")
    print(f"Written to {out}")


if __name__ == "__main__":
    main()
