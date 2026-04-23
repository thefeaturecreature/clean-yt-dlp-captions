# Functions

## clean_captions.py

| Function | Description |
|---|---|
| `fetch_metadata(url, browser)` | Runs `yt-dlp --dump-json` to get video metadata as a dict |
| `fetch_subtitles(url, output_dir, lang, browser)` | Downloads auto-generated VTT subtitles via yt-dlp |
| `clean_vtt(path)` | Parses a VTT file into a deduplicated list of text lines, stripping timestamps, tags, sound cues, and artifacts |
| `join_sentences(lines)` | Joins subtitle lines into sentence-level paragraphs on punctuation boundaries |
| `format_date(raw)` | Converts YYYYMMDD string to YYYY-MM-DD |
| `build_header(meta)` | Builds a markdown header block from yt-dlp metadata (title, channel, URL, date, duration, description) |
| `main()` | CLI entry point — accepts a URL or local .vtt file, orchestrates fetch → clean → write |
