# clean-yt-dlp-captions

Downloads captions from a video URL via yt-dlp, cleans up auto-generated subtitle artifacts, and produces a polished markdown transcript. Optionally runs the transcript through any OpenAI-compatible LLM to fix transcription errors and add semantic paragraph breaks.

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
# fill in your LLM credentials and paths
```

## Configuration (`.env`)

```env
LLM_API_KEY=your_key_here
LLM_MODEL=open-mistral-7b
LLM_BASE_URL=https://api.mistral.ai/v1

# Optional — defaults to ~/Downloads
OUTPUT_DIR=~/Documents/your/output/path
VTT_DIR=~/Downloads
```

The script uses any OpenAI-compatible API endpoint. Point `LLM_BASE_URL` and `LLM_MODEL` at whichever provider you have a key for.

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

# Override model for this run
python3 clean_captions.py --llm --model gpt-4o-mini https://www.youtube.com/watch?v=...

# Process a local .vtt file instead
python3 clean_captions.py --llm file.en.vtt
```

## Authentication (cookies)

YouTube and other sites may block unauthenticated yt-dlp requests or restrict certain content. Pass cookies directly from your browser to authenticate:

```bash
python3 clean_captions.py --cookies-from-browser chrome https://www.youtube.com/watch?v=...
# or firefox, safari, edge, brave, etc.
```

You must be logged in to the site in that browser. yt-dlp reads the cookie store directly — no export needed.

## Output

Each run produces a `[slug].md` file in `OUTPUT_DIR` containing:

- Title, channel, URL, publish date, and duration
- The video description
- The cleaned transcript body
