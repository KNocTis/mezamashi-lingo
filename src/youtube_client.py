import os
import datetime
import json
import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

logger = logging.getLogger(__name__)

from .config import settings

class YouTubeClient:
    def __init__(self, api_key=None, cache_dir='.cache'):
        self.api_key = api_key or settings.youtube_api_key
        self._service = None
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    @property
    def youtube(self):
        """Returns a thread-local-safe YouTube service instance."""
        if self._service is None:
            self._service = build('youtube', 'v3', developerKey=self.api_key)
        return self._service

    def _get_cache(self, key, ttl_seconds=600):
        """Retrieves data from cache if it hasn't expired."""
        cache_path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(cache_path):
            if time.time() - os.path.getmtime(cache_path) < ttl_seconds:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        return None

    def _set_cache(self, key, data):
        """Saves data to cache."""
        cache_path = os.path.join(self.cache_dir, f"{key}.json")
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def get_uploads_playlist_id(self, channel_id):
        """Retrieves the uploads playlist ID for a given channel ID."""
        cache_key = f"playlist_id_{channel_id}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            request = self.youtube.channels().list(
                part="contentDetails",
                id=channel_id
            )
            response = request.execute()
            
            # Log raw response at INFO level as requested
            logger.info(f"[RAW_API] channels.list: {json.dumps(response, ensure_ascii=False)}")

            if not response.get('items'):
                logger.error(f"No channel found with ID: {channel_id}")
                return None

            playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            self._set_cache(cache_key, playlist_id)
            return playlist_id
        except HttpError as e:
            logger.error(f"HTTP error occurred: {e}")
            return None

    def get_recent_videos(self, playlist_id, hours=24):
        """Fetches videos from a playlist uploaded within the last N hours."""
        cache_key = f"recent_videos_{playlist_id}"
        cached = self._get_cache(cache_key, ttl_seconds=300) # shorter cache for recent videos
        if cached:
            return cached

        videos = []
        now = datetime.datetime.now(datetime.timezone.utc)
        since = now - datetime.timedelta(hours=hours)

        try:
            request = self.youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50
            )
            response = request.execute()
            
            # Log raw response at INFO level as requested
            logger.info(f"[RAW_API] playlistItems.list: {json.dumps(response, ensure_ascii=False)}")

            for item in response.get('items', []):
                published_at_str = item['snippet']['publishedAt']
                published_at = datetime.datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))

                if published_at >= since:
                    videos.append({
                        'title': item['snippet']['title'],
                        'url': f"https://www.youtube.com/watch?v={item['snippet']['resourceId']['videoId']}",
                        'published_at': published_at_str,
                        'video_id': item['snippet']['resourceId']['videoId']
                    })
                else:
                    break

            self._set_cache(cache_key, videos)
            return videos
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                logger.error("YouTube API quota exceeded.")
            else:
                logger.error(f"HTTP error occurred while fetching playlist items: {e}")
            return []

    def get_video_durations(self, video_ids):
        """Fetches durations for a list of video IDs and returns a mapping {video_id: duration_seconds}."""
        if not video_ids:
            return {}
        
        # Check cache for each ID
        durations = {}
        missing_ids = []
        for vid in video_ids:
            cached = self._get_cache(f"duration_{vid}", ttl_seconds=86400) # Durations don't change
            if cached is not None:
                durations[vid] = cached
            else:
                missing_ids.append(vid)

        if not missing_ids:
            return durations

        try:
            # YouTube API allows up to 50 IDs per request
            for i in range(0, len(missing_ids), 50):
                batch = missing_ids[i:i+50]
                request = self.youtube.videos().list(
                    part="contentDetails",
                    id=",".join(batch)
                )
                response = request.execute()
                
                # Log raw response at INFO level as requested
                logger.info(f"[RAW_API] videos.list: {json.dumps(response, ensure_ascii=False)}")

                for item in response.get('items', []):
                    duration_str = item['contentDetails']['duration']
                    seconds = self._parse_duration(duration_str)
                    durations[item['id']] = seconds
                    self._set_cache(f"duration_{item['id']}", seconds)
            
            return durations
        except HttpError as e:
            logger.error(f"Error fetching video durations: {e}")
            return {}

    def get_video_info(self, video_id):
        """Fetches metadata for a specific video ID."""
        cache_key = f"video_info_{video_id}"
        cached = self._get_cache(cache_key, ttl_seconds=86400)
        if cached:
            return cached

        try:
            request = self.youtube.videos().list(
                part="snippet,contentDetails",
                id=video_id
            )
            response = request.execute()
            
            logger.info(f"[RAW_API] videos.list (single): {json.dumps(response, ensure_ascii=False)}")

            if not response.get('items'):
                logger.error(f"No video found with ID: {video_id}")
                return None

            item = response['items'][0]
            video_info = {
                'title': item['snippet']['title'],
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'published_at': item['snippet']['publishedAt'],
                'video_id': video_id,
                'duration_sec': self._parse_duration(item['contentDetails']['duration']),
                'thumbnail_url': item['snippet']['thumbnails'].get('high', {}).get('url')
            }
            
            self._set_cache(cache_key, video_info)
            return video_info
        except HttpError as e:
            logger.error(f"Error fetching video info: {e}")
            return None

    def _parse_duration(self, duration_str):
        """Parses ISO 8601 duration (e.g., PT3M45S) into total seconds."""
        import re
        # Pattern for PT#H#M#S
        pattern = re.compile(r'PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?')
        match = pattern.match(duration_str)
        if not match:
            return 0
        
        hours = int(match.group('hours') or 0)
        minutes = int(match.group('minutes') or 0)
        seconds = int(match.group('seconds') or 0)
        
        return hours * 3600 + minutes * 60 + seconds
