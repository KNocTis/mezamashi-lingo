import logging
import random
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
from .youtube_client import YouTubeClient
from .llm_client import LLMClient
from .models import VideoMetadata, HistoryEntry
from .repository import Repository
from .config import settings

logger = logging.getLogger(__name__)

class VideoFetcher:
    def __init__(self, youtube_client: YouTubeClient, llm_client: Optional[LLMClient] = None):
        self.client = youtube_client
        self.llm_client = llm_client

    def fetch_daily_videos(self, force: bool = False) -> Dict[str, Optional[VideoMetadata]]:
        """Fetches and selects one video for each language."""
        from datetime import datetime
        channels = Repository.load_channels()
        if not channels:
            logger.warning("No channels loaded. Check channels.json.")
            return {}

        # Load history to avoid duplicates
        history_data = Repository.load_history()
        seen_ids = {h.id for h in history_data}
        history_map = {h.video_id: h for h in history_data}

        # Check existing selections for today
        raw_selection = Repository.load_raw_selection()
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        already_selected_langs = {}
        if raw_selection and not force:
            for item in raw_selection:
                if item.get("date_picked") == today_str:
                    vid = item.get("video_id")
                    if vid in history_map:
                        h = history_map[vid]
                        if h.lang:
                            already_selected_langs[h.lang] = h

        videos_by_lang: Dict[str, List[VideoMetadata]] = {'en': [], 'ja': []}

        def process_channel(channel):
            channel_id = channel.id
            lang_attr = channel.lang
            
            if not channel_id or lang_attr not in videos_by_lang:
                return None

            if lang_attr in already_selected_langs:
                return None

            try:
                # Use a new client instance for thread safety if needed, 
                # but YouTubeClient.youtube property is already lazy-loaded.
                # To be extra safe in threads, we can pass the api_key.
                local_client = YouTubeClient(self.client.api_key)
                playlist_id = local_client.get_uploads_playlist_id(channel_id)
                if playlist_id:
                    recent_videos = local_client.get_recent_videos(playlist_id)
                    metadata_list = []
                    for v in recent_videos:
                        metadata = VideoMetadata(**v)
                        metadata.lang = lang_attr
                        metadata_list.append(metadata)
                    return (lang_attr, metadata_list)
            except Exception as e:
                logger.error(f"Error fetching channel {channel.name}: {e}")
            return None

        # Execute in parallel
        logger.info(f"Fetching updates for {len(channels)} channels in parallel (workers=2)...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(process_channel, channels))

        for result in results:
            if result:
                lang_attr, videos = result
                videos_by_lang[lang_attr].extend(videos)

        # Fetch durations for all candidate videos
        all_video_ids = []
        for videos in videos_by_lang.values():
            all_video_ids.extend([v.video_id for v in videos])
        
        durations = self.client.get_video_durations(all_video_ids)

        selected_videos: Dict[str, Optional[VideoMetadata]] = {}
        newly_selected_entries: List[HistoryEntry] = []

        for lang, videos in videos_by_lang.items():
            if lang in already_selected_langs:
                logger.info(f"Using already selected {lang} video from today: {already_selected_langs[lang].title}")
                selected_videos[lang] = VideoMetadata(**already_selected_langs[lang].model_dump())
                continue

            # Attach duration to video objects
            for v in videos:
                v.duration_sec = durations.get(v.video_id, 0)
            
            # Filtering logic: Max duration AND not in history
            candidates = [
                v for v in videos 
                if 0 < v.duration_sec <= settings.max_video_duration_sec 
                and v.video_id not in seen_ids
            ]

            if not candidates:
                logger.warning(f"No recent/unseen videos found for language: {lang}")
                selected_videos[lang] = None
                continue

            # Selection Logic: Use LLM if available, otherwise random
            if self.llm_client:
                # Filter recent titles for this specific language
                lang_recent_titles = [h.title for h in history_data if h.lang == lang][-10:]
                
                logger.info(f"Using LLM to select best {lang} video from {len(candidates)} candidates.")
                selected_videos[lang] = self.llm_client.select_best_video(lang, candidates, lang_recent_titles)
            else:
                selected_videos[lang] = random.choice(candidates)
                logger.info(f"Selected {lang} video (random): {selected_videos[lang].title}")

            if selected_videos[lang]:
                newly_selected_entries.append(HistoryEntry(
                    **selected_videos[lang].model_dump()
                ))

        # Update history with new selections
        if newly_selected_entries:
            Repository.save_history(newly_selected_entries)

        return selected_videos
    def fetch_video_by_url(self, url: str) -> Optional[VideoMetadata]:
        """Fetches metadata for a specific YouTube URL."""
        video_id = self._extract_video_id(url)
        if not video_id:
            logger.error(f"Could not extract video ID from URL: {url}")
            return None

        video_info = self.client.get_video_info(video_id)
        if not video_info:
            return None

        metadata = VideoMetadata(**video_info)
        
        # Detect language if possible, otherwise default to 'en' or ask?
        # For now, let's try to detect from title or just default to 'en'
        # Actually, let's just let it be None and handle it in the workflow
        return metadata

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extracts the video ID from a YouTube URL."""
        import re
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'youtu\.be\/([0-9A-Za-z_-]{11})',
            r'embed\/([0-9A-Za-z_-]{11})',
            r'\/v\/([0-9A-Za-z_-]{11})',
            r'\/videos\/([0-9A-Za-z_-]{11})',
            r'\/watch\?v=([0-9A-Za-z_-]{11})'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
