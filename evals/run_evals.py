#!/usr/bin/env python3
"""
Eval runner for transcript cleaning and speaker attribution.

For each video in videos.yaml:
  1. Download VTT if not already cached in evals/vtts/
  2. Run through the clean pipeline (--raw mode for attribution)
  3. Save output to evals/results/
  4. Compare against reference in evals/references/ if one exists
  5. Print a per-video score summary

References are manually-verified transcripts placed at evals/references/<id>.md.
Scoring uses an LLM call to compare output against reference on a rubric.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

EVALS_DIR = Path(__file__).parent
VTTS_DIR = EVALS_DIR / "vtts"
RESULTS_DIR = EVALS_DIR / "results"
REFERENCES_DIR = EVALS_DIR / "references"

SCORE_PROMPT = """\
You are an evaluator comparing an auto-generated transcript against a verified reference.

Score the output on each criterion from 0–10:
- speaker_accuracy: Are speakers correctly identified and labelled throughout?
- error_correction: Are transcription errors (mis-heard words, proper nouns) fixed?
- readability: Are paragraph breaks and sentence joining natural and readable?

Return a JSON object with:
- "speaker_accuracy": <0-10>
- "error_correction": <0-10>
- "readability": <0-10>
- "notes": one or two sentences on the biggest issues

Return only the JSON object, no markdown fencing.\
"""


def load_videos() -> list[dict]:
    with open(EVALS_DIR / "videos.yaml") as f:
        return yaml.safe_load(f)["videos"]


def find_cached_vtt(video_id: str) -> Path | None:
    matches = list(VTTS_DIR.glob(f"*[{video_id}]*.vtt"))
    return matches[0] if matches else None


def download_vtt(url: str, video_id: str, browser: str | None = None) -> Path:
    VTTS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "--write-auto-sub", "--skip-download",
        "--sub-lang", "en", "--sub-format", "vtt",
        "--output", str(VTTS_DIR / "%(title)s [%(id)s].%(ext)s"),
    ]
    if browser:
        cmd += ["--cookies-from-browser", browser]
    cmd.append(url)
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    vtt = find_cached_vtt(video_id)
    if not vtt:
        raise FileNotFoundError(f"VTT not found after download for {video_id}")
    return vtt


def run_pipeline(vtt_path: Path, model: str) -> str:
    """Run clean_captions.py in --raw --llm mode, return output path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent.parent / "clean_captions.py"),
         "--llm", "--raw", f"--output={RESULTS_DIR / (vtt_path.stem + '.md')}",
         str(vtt_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return RESULTS_DIR / (vtt_path.stem + ".md")


def score_output(output_path: Path, reference_path: Path, model: str) -> dict:
    from openai import OpenAI
    api_key = os.environ.get("LLM_API_KEY")
    client = OpenAI(api_key=api_key, base_url=os.environ.get("LLM_BASE_URL"), timeout=60)

    output = output_path.read_text()
    reference = reference_path.read_text()
    prompt = f"REFERENCE:\n{reference}\n\nOUTPUT TO EVALUATE:\n{output}"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SCORE_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.strip("```json").strip("```").strip()
    return json.loads(raw)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run transcript evals.")
    parser.add_argument("--browser", default="chrome", help="Browser for yt-dlp cookies")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "open-mistral-7b"))
    parser.add_argument("--skip-download", action="store_true", help="Use cached VTTs only")
    parser.add_argument("--id", help="Run only the video with this ID")
    args = parser.parse_args()

    videos = load_videos()
    if args.id:
        videos = [v for v in videos if v["id"] == args.id]
        if not videos:
            print(f"No video found with id {args.id}", file=sys.stderr)
            sys.exit(1)

    print(f"Running evals on {len(videos)} video(s) with model {args.model}\n")
    summary = []

    for video in videos:
        vid_id = video["id"]
        print(f"── {video['title']} [{vid_id}]")

        # Download or find cached VTT
        vtt = find_cached_vtt(vid_id)
        if not vtt:
            if args.skip_download:
                print(f"   SKIP — no cached VTT and --skip-download set\n")
                continue
            print("   Downloading VTT…")
            try:
                vtt = download_vtt(video["url"], vid_id, browser=args.browser)
            except Exception as e:
                print(f"   ERROR downloading: {e}\n")
                continue

        # Run pipeline
        print("   Running pipeline…")
        try:
            output_path = run_pipeline(vtt, args.model)
        except Exception as e:
            print(f"   ERROR in pipeline: {e}\n")
            continue
        print(f"   Output: {output_path}")

        # Score if reference exists (yaml override or default convention)
        ref_path = EVALS_DIR / video["reference"] if "reference" in video else REFERENCES_DIR / f"{vid_id}.md"
        if ref_path.exists():
            print("   Scoring against reference…")
            time.sleep(1)
            try:
                scores = score_output(output_path, ref_path, args.model)
                summary.append({"id": vid_id, "title": video["title"], **scores})
                print(f"   Speaker accuracy: {scores.get('speaker_accuracy')}/10")
                print(f"   Error correction: {scores.get('error_correction')}/10")
                print(f"   Readability:      {scores.get('readability')}/10")
                print(f"   Notes: {scores.get('notes')}")
            except Exception as e:
                print(f"   ERROR scoring: {e}")
        else:
            print("   No reference found — add one to evals/references/{vid_id}.md to enable scoring")
        print()

    if summary:
        print("── Summary ──")
        for row in summary:
            avg = (row["speaker_accuracy"] + row["error_correction"] + row["readability"]) / 3
            print(f"{row['title'][:50]:<50}  avg {avg:.1f}/10")


if __name__ == "__main__":
    main()
