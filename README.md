# Mezamashi Lingo

Mezamashi Lingo is a daily video fetcher, transcriber, and translator designed for language learners. It automatically finds the best videos from your favorite YouTube channels, transcribes them using Whisper, and generates bilingual subtitles with LLM-powered translation.

## 🚀 Getting Started

### 1. Environment Setup
This project uses a local virtual environment. Please refer to [ENVIRONMENT.md](docs/ENVIRONMENT.md) for details on how to run commands correctly.

### 2. Configuration
Copy the template and fill in your API keys:
```bash
cp .env.template .env
```

### 3. Usage

The script is designed to be flexible, supporting both automated daily runs and manual processing of specific videos.

#### **A. Daily Fetch (Full Pipeline)**
Runs the entire workflow for all configured channels: fetch, download, transcribe, generate vocabulary, and translate.
```bash
./venv/bin/python main.py
```

#### **B. Single Video Processing**
Process a specific video by its URL or ID.
```bash
# Using a full URL
./venv/bin/python main.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Using just the Video ID (if it exists in history)
./venv/bin/python main.py VIDEO_ID

# Override detected language
./venv/bin/python main.py VIDEO_ID --lang ja
```

#### **C. Running Specific Phases**
You can run only specific parts of the pipeline using the `--phase` argument.

| Phase | Description |
| :--- | :--- |
| `fetch` | Detect and select new videos from your `channels.json`. |
| `download` | Download selected videos to `downloads/[YYYYMMDD]/`. |
| `transcribe` | Perform vocal separation and generate `_transcription.json` and `.srt`. |
| `vocabulary` | Generate vocabulary `_vocab.json` (LLM) and `_vocab.html` (Table). |
| `glossary` | Regenerate the premium HTML glossary from existing JSON data. |
| `translate` | Generate bilingual subtitles (`.chs.srt`). |

**Example:**
```bash
# Only regenerate the HTML glossary for a video
./venv/bin/python main.py VIDEO_ID --phase glossary
```

## 📂 Output Structure
Downloaded videos and generated assets are organized by date:
- `downloads/[YYYYMMDD]/[video_id]_[title].mp4`: Main video.
- `downloads/[YYYYMMDD]/[video_id]_[title]_vocab.html`: Premium vocabulary table.
- `downloads/[YYYYMMDD]/[video_id]_[title].chs.srt`: Bilingual subtitles.
- `downloads/vocals/[video_id]_[title]_vocals.wav`: Separated vocal track.

## 🏗 Architecture
The project follows a modular architecture:
- `src/models.py`: Structured data models using Pydantic.
- `src/config.py`: Centralized configuration management.
- `src/repository.py`: Persistence layer for state and history.
- `templates/`: HTML templates for premium output generation.
- `main.py`: Orchestration via `WorkflowManager`.

## 📄 License
MIT
