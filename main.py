import logging
import argparse
import os
import json
from typing import Dict, List, Optional

from src.config import settings
from src.models import VideoMetadata, TranscriptionSegment, GlossaryTerm, HistoryEntry
from src.repository import Repository
from src.llm_client import LLMClient
from src.youtube_client import YouTubeClient
from src.fetcher import VideoFetcher
from src.downloader import VideoDownloader
from src.transcriber import VideoTranscriber
from src.translator import SubtitleTranslator

# Configure logging
os.makedirs(settings.log_dir, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(settings.log_dir, "daily_fetcher.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class WorkflowManager:
    def __init__(self):
        self.llm_client = LLMClient()
        self.youtube_client = YouTubeClient()
        self.fetcher = VideoFetcher(self.youtube_client, self.llm_client)
        self.downloader = VideoDownloader()
        self.transcriber = VideoTranscriber()
        self.translator = SubtitleTranslator(self.llm_client)

    def run_fetch(self) -> Dict[str, Optional[VideoMetadata]]:
        logger.info("PHASE 1: Starting daily video fetch...")
        selected = self.fetcher.fetch_daily_videos()
        if selected:
            # Filter out None values and convert to list for saving
            active_selections = [v for v in selected.values() if v]
            Repository.save_selection(active_selections)
            
            print("\n--- Selected Videos ---")
            print(json.dumps([v.model_dump(mode='json') for v in active_selections], indent=2, ensure_ascii=False))
        return selected

    def run_download(self, selected: Dict[str, Optional[VideoMetadata]]) -> List[VideoMetadata]:
        logger.info("PHASE 2: Starting video downloads...")
        downloaded = self.downloader.download_videos(selected)
        if downloaded:
            print("\n--- Downloaded Files ---")
            for f in downloaded:
                print(f"[{f.lang.upper()}] {f.local_path}")
        return downloaded

    def run_transcribe(self, downloaded: List[VideoMetadata]) -> List[tuple]:
        logger.info("PHASE 3: Starting transcription...")
        results = []
        for video in downloaded:
            # Check if transcription already exists
            base_path = os.path.splitext(video.local_path)[0]
            json_path = f"{base_path}_transcription.json"
            
            if os.path.exists(json_path):
                logger.info(f"Loading existing transcription: {json_path}")
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    segments = [TranscriptionSegment(**s) for s in data]
                results.append((video, json_path, segments))
            else:
                segments = self.transcriber.transcribe(video.local_path, language=video.lang)
                if segments:
                    self.transcriber.save_transcription(segments, json_path)
                    print(f"[{video.lang.upper()}] Transcription completed.")
                    results.append((video, json_path, segments))
        return results

    def run_vocabulary(self, transcriptions: List[tuple]):
        logger.info("PHASE 4: Starting vocabulary generation (JSON)...")
        for video, json_path, segments in transcriptions:
            vocab_path = os.path.splitext(video.local_path)[0] + "_vocab.json"
            
            glossary = None
            if os.path.exists(vocab_path):
                try:
                    with open(vocab_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        glossary = [GlossaryTerm(**g) if isinstance(g, dict) else g for g in data]
                    logger.info(f"Loaded existing glossary: {vocab_path}")
                except Exception as e:
                    logger.warning(f"Failed to load glossary: {e}")
            
            if not glossary:
                logger.info(f"Building new glossary for {video.lang} video: {video.local_path}")
                glossary = self.translator.build_glossary(segments, source_lang=video.lang)
                if glossary:
                    with open(vocab_path, 'w', encoding='utf-8') as f:
                        json.dump([g.model_dump(mode='json') for g in glossary], f, ensure_ascii=False, indent=2)
                    print(f"[{video.lang.upper()}] Vocabulary JSON generated.")
            
            # Also generate HTML by default when running vocabulary phase
            self.run_glossary([(video, json_path, segments)])

    def run_glossary(self, transcriptions: List[tuple]):
        logger.info("PHASE 4.5: Starting glossary HTML generation...")
        for video, json_path, segments in transcriptions:
            base_path = os.path.splitext(video.local_path)[0]
            vocab_path = f"{base_path}_vocab.json"
            html_path = f"{base_path}_vocab.html"
            
            if os.path.exists(vocab_path):
                try:
                    template_path = os.path.join(settings.templates_dir, "glossary_template.html")
                    if os.path.exists(template_path):
                        with open(template_path, 'r', encoding='utf-8') as f:
                            template = f.read()
                        
                        with open(vocab_path, 'r', encoding='utf-8') as f:
                            glossary_json = f.read()
                        
                        from datetime import datetime
                        html_content = template.replace("{{ VIDEO_TITLE }}", video.title)
                        html_content = html_content.replace("{{ VIDEO_ID }}", video.video_id)
                        html_content = html_content.replace("{{ GENERATED_DATE }}", datetime.now().strftime("%Y-%m-%d %H:%M"))
                        html_content = html_content.replace("{{ GLOSSARY_JSON }}", glossary_json)
                        
                        with open(html_path, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                        print(f"[{video.lang.upper()}] Vocabulary HTML generated: {html_path}")
                except Exception as e:
                    logger.error(f"Failed to generate HTML glossary: {e}")
            else:
                logger.warning(f"No glossary JSON found for {video.video_id}. Run 'vocabulary' phase first.")

    def run_translate(self, transcriptions: List[tuple]):
        logger.info("PHASE 4: Starting translation...")
        for video, json_path, segments in transcriptions:
            bilingual_srt = os.path.splitext(video.local_path)[0] + ".chs.srt"
            vocab_path = os.path.splitext(video.local_path)[0] + "_vocab.json"
            
            logger.info(f"Processing {video.lang} video: {video.local_path}")
            
            # Load Glossary (required for consistent translation)
            glossary = None
            if os.path.exists(vocab_path):
                try:
                    with open(vocab_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        glossary = [GlossaryTerm(**g) if isinstance(g, dict) else g for g in data]
                    logger.info(f"Loaded existing glossary: {vocab_path}")
                except Exception as e:
                    logger.warning(f"Failed to load glossary: {e}")
            
            if not glossary:
                logger.info(f"Glossary missing. Building before translation...")
                glossary = self.translator.build_glossary(segments, source_lang=video.lang)
                if glossary:
                    with open(vocab_path, 'w', encoding='utf-8') as f:
                        json.dump([g.model_dump(mode='json') for g in glossary], f, ensure_ascii=False, indent=2)
            
            # 2. Translate
            all_translated = []
            for chunk_results in self.translator.translate_segments(segments, source_lang=video.lang, glossary=glossary):
                all_translated.extend(chunk_results)
                
                # Incremental Save
                remaining = segments[len(all_translated):]
                current_data = all_translated + remaining
                self.transcriber.save_transcription(current_data, json_path)
                self.translator.save_bilingual_srt(current_data, bilingual_srt)
                
                logger.info(f"[{video.lang.upper()}] Progress: {len(all_translated)}/{len(segments)}")
            
            print(f"[{video.lang.upper()}] Translation completed.")

    def run_single_fetch(self, url: str, lang: Optional[str] = None) -> Dict[str, Optional[VideoMetadata]]:
        logger.info(f"Fetching metadata for single video: {url}")
        video = self.fetcher.fetch_video_by_url(url)
        if video:
            if lang:
                video.lang = lang
            elif not video.lang:
                video.lang = 'en' # Default to en if not specified and not detected
                logger.info(f"No language specified/detected. Defaulting to '{video.lang}'.")
            
            # Save to selection to keep consistency with the workflow
            Repository.save_selection([video])
            
            # Also save to history so it's marked as seen
            Repository.save_history([HistoryEntry(**video.model_dump())])
            
            print("\n--- Selected Video ---")
            print(json.dumps(video.model_dump(mode='json'), indent=2, ensure_ascii=False))
            return {video.lang: video}
        return {}

def main():
    parser = argparse.ArgumentParser(description="Mezamashi Lingo: Daily video fetcher and transcriber.")
    parser.add_argument('url_pos', type=str, nargs='?', help="YouTube video URL to process")
    parser.add_argument('--phase', type=str, default='all', choices=['all', 'fetch', 'download', 'transcribe', 'vocabulary', 'glossary', 'translate'],
                        help="Specific phase to run")
    parser.add_argument('--url', type=str, help="YouTube video URL to process (named argument)")
    parser.add_argument('--lang', type=str, help="Language of the video (if URL is used)")
    args = parser.parse_args()

    # Resolve URL: positional or named
    url = args.url_pos or args.url

    manager = WorkflowManager()
    
    selected_dict = {}
    downloaded_list = []
    transcriptions = []

    # 1. Fetch
    if url:
        # Check if it's a URL or an ID
        if url.startswith('http') or 'youtube.com' in url or 'youtu.be' in url:
            selected_dict = manager.run_single_fetch(url, args.lang)
        else:
            # Assume it's a Video ID
            logger.info(f"Using video ID from command line: {url}")
            history = Repository.load_history()
            history_map = {h.video_id: h for h in history}
            if url in history_map:
                video = VideoMetadata(**history_map[url].model_dump())
                if args.lang:
                    video.lang = args.lang
                Repository.save_selection([video])
                selected_dict = {video.lang: video}
            else:
                logger.error(f"Video ID {url} not found in history. Please provide a full URL to fetch it.")
                return
    elif args.phase in ['all', 'fetch']:
        selected_dict = manager.run_fetch()
    else:
        # Load from selection file (already hydrates from history in Repository.load_selection)
        selection_list = Repository.load_selection()
        selected_dict = {v.lang: v for v in selection_list}

    # 2. Download
    if args.phase in ['all', 'download', 'transcribe', 'vocabulary', 'glossary', 'translate']:
        downloaded_list = manager.run_download(selected_dict)

    # 3. Transcribe
    if args.phase in ['all', 'transcribe', 'vocabulary', 'glossary', 'translate']:
        transcriptions = manager.run_transcribe(downloaded_list)

    # 4. Vocabulary
    if args.phase in ['all', 'vocabulary', 'translate']:
        manager.run_vocabulary(transcriptions)
    
    # 4.5 Glossary HTML
    if args.phase == 'glossary':
        manager.run_glossary(transcriptions)

    # 5. Translate
    if args.phase in ['all', 'translate']:
        manager.run_translate(transcriptions)

    logger.info(f"Execution completed.")

if __name__ == "__main__":
    main()
