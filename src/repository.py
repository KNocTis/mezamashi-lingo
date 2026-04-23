import json
import os
import logging
from typing import List, Optional
from .models import ChannelConfig, HistoryEntry, VideoMetadata
from .config import settings

logger = logging.getLogger(__name__)

class Repository:
    @staticmethod
    def load_channels() -> List[ChannelConfig]:
        if not os.path.exists(settings.channels_file):
            logger.warning(f"Channels file not found: {settings.channels_file}")
            return []
        try:
            with open(settings.channels_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [ChannelConfig(**c) for c in data.get('channels', [])]
        except Exception as e:
            logger.error(f"Error loading channels: {e}")
            return []

    @staticmethod
    def load_history() -> List[HistoryEntry]:
        if not os.path.exists(settings.history_file):
            return []
        try:
            with open(settings.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [HistoryEntry(**h) for h in data]
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            return []

    @staticmethod
    def save_history(entries: List[HistoryEntry]):
        try:
            # Keep only the last 50 entries
            history = Repository.load_history()
            history.extend(entries)
            history = history[-50:]
            
            with open(settings.history_file, 'w', encoding='utf-8') as f:
                # Convert to dict and handle datetime serialization
                json_data = [h.model_dump(mode='json') for h in history]
                json.dump(json_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving history: {e}")

    @staticmethod
    def save_selection(videos: List[VideoMetadata]):
        try:
            with open(settings.selection_file, 'w', encoding='utf-8') as f:
                # Save only the IDs as requested
                json_data = [{"video_id": v.video_id} for v in videos]
                json.dump(json_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving selection: {e}")

    @staticmethod
    def load_selection() -> List[VideoMetadata]:
        if not os.path.exists(settings.selection_file):
            return []
        try:
            with open(settings.selection_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                selected_ids = [v.get("video_id") for v in data]
            
            # Hydrate from history
            history = Repository.load_history()
            history_map = {h.video_id: h for h in history}
            
            results = []
            for vid in selected_ids:
                if vid in history_map:
                    # Convert HistoryEntry back to VideoMetadata
                    h = history_map[vid]
                    results.append(VideoMetadata(**h.model_dump()))
                else:
                    logger.warning(f"Video {vid} in selection but not in history.")
            return results
        except Exception as e:
            logger.error(f"Error loading selection: {e}")
            return []
