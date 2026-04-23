# clean-yt-dlp-captions

Downloads captions from a video URL via yt-dlp, cleans up auto-generated subtitle artifacts, and produces a polished markdown transcript. Optionally runs the transcript through Mistral to fix transcription errors and add semantic paragraph breaks.

## Requirements

- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) installed and on your PATH

```bash
brew install yt-dlp
# or
pip install yt-dlp
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# add your Mistral API key to .env
```

## Usage

```bash
# Basic — download and clean captions from a URL
python3 clean_captions.py https://www.youtube.com/watch?v=...

# Clean via LLM (fixes errors, adds semantic paragraph breaks)
python3 clean_captions.py --llm https://www.youtube.com/watch?v=...

# Join lines into sentence paragraphs (heuristic, no API call)
python3 clean_captions.py --join https://www.youtube.com/watch?v=...

# Specify output file
python3 clean_captions.py --llm --output transcript.md https://www.youtube.com/watch?v=...

# Different subtitle language
python3 clean_captions.py --lang es https://www.youtube.com/watch?v=...

# Process a local .vtt file instead
python3 clean_captions.py --llm file.en.vtt
```

Downloaded `.vtt` files go to `downloads/` and finished transcripts go to `output/` — both are gitignored.

## Authentication (cookies)

YouTube and other sites may block unauthenticated yt-dlp requests or restrict certain content. Pass cookies directly from your browser to authenticate:

```bash
python3 clean_captions.py --cookies-from-browser chrome https://www.youtube.com/watch?v=...
# or firefox, safari, edge, brave, etc.
```

You must be logged in to the site in that browser. yt-dlp reads the cookie store directly — no export needed.

## Output

Each run produces a `[Title].md` file containing:

- Title, channel, URL, publish date, and duration
- The video description
- The cleaned transcript body

## LLM cleaning

`--llm` passes the transcript through an LLM to fix proper noun errors (e.g. auto-CC mishearing technical terms) and add topic-based paragraph breaks.

The default provider is Mistral. Since Mistral's API is OpenAI-compatible, you can point it at any compatible endpoint by swapping the model name and API key in `.env`. Use `--model` to specify a different model:

```bash
python3 clean_captions.py --llm --model mistral-small-latest https://...
```
