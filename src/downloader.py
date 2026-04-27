import os
import yt_dlp
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from .models import VideoMetadata
from .config import settings
from typing import Dict, List, Optional

class VideoDownloader:
    def __init__(self, download_path=None):
        self.download_path = download_path or settings.download_dir
        
        # Fallback logic: if primary path is unavailable, use fallback
        try:
            os.makedirs(self.download_path, exist_ok=True)
            # Extra check: is it actually writable?
            if not os.access(self.download_path, os.W_OK):
                raise OSError("Directory not writable")
        except (OSError, IOError) as e:
            logger.warning(f"Primary download path '{self.download_path}' unavailable: {e}. Using fallback.")
            self.download_path = settings.fallback_download_dir
            os.makedirs(self.download_path, exist_ok=True)
        
        logger.info(f"Active download directory: {self.download_path}")

    def download_videos(self, selected_videos: Dict[str, Optional[VideoMetadata]]) -> List[VideoMetadata]:
        """Downloads the selected videos for each language."""
        if not selected_videos:
            return []

        downloaded_files: List[VideoMetadata] = []
        
        for lang, video in selected_videos.items():
            if not video:
                continue
            
            # Format the filename: [video_id]_[clean_title]
            date_str = datetime.now().strftime("%Y%m%d")
            clean_title = "".join([c for c in video.title if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_')
            filename = f"{video.video_id}_{clean_title[:50]}"
            
            target_dir = os.path.join(self.download_path, date_str)
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, f"{filename}.mp4")
            
            # Skip if already exists
            if os.path.exists(target_path):
                logger.info(f"Skipping download, file already exists: {target_path}")
                video.local_path = target_path
                downloaded_files.append(video)
                continue

            logger.info(f"Downloading {video.lang} video: {video.title}")
            
            # Configure yt-dlp options
            ydl_opts = {
                'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
                'outtmpl': os.path.join(target_dir, f"{filename}.%(ext)s"),
                'merge_output_format': 'mp4',
                'quiet': False,
                'no_warnings': True,
                'logger': logger,
                'remote_components': ['ejs:github'],
                # If still getting "VPN/Proxy Detected", ensure you are logged into YouTube in Chrome.
                'cookiesfrombrowser': ('chrome',), 
            }
            
            try:
                # video.url is missing in VideoMetadata, I should add it.
                # Actually, I'll use video_id to construct url if needed.
                video_url = f"https://www.youtube.com/watch?v={video.video_id}"
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    filepath = ydl.prepare_filename(info)
                    # If yt-dlp merged it to mp4, the filepath should be updated
                    if not filepath.endswith('.mp4') and os.path.exists(filepath.rsplit('.', 1)[0] + '.mp4'):
                        filepath = filepath.rsplit('.', 1)[0] + '.mp4'

                    video.local_path = filepath
                    downloaded_files.append(video)
                    logger.info(f"Successfully downloaded: {filepath}")
            except Exception as e:
                logger.error(f"Failed to download {video.video_id}: {e}")
        
        return downloaded_files
