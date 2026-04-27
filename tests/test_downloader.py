import os
import pytest
from unittest.mock import patch
from src.downloader import VideoDownloader
from src.config import settings

def test_downloader_fallback_to_local(tmp_path):
    """Verify that downloader falls back to local storage if primary path is unreachable."""
    
    # Create a temporary directory for the fallback
    fallback_dir = tmp_path / "local_fallback"
    fallback_dir.mkdir()
    
    # Mock settings
    with patch('src.downloader.settings') as mock_settings:
        # Use an absolute path that definitely doesn't exist and can't be created (no permission)
        # On Mac/Linux, /Volumes/NonExistent usually requires root to create
        mock_settings.download_dir = "/Volumes/NonExistentNAS_Mezamashi"
        mock_settings.fallback_download_dir = str(fallback_dir)
        
        # Initialize downloader
        # This should trigger the OSError in __init__ and switch to fallback
        downloader = VideoDownloader()
        
        assert downloader.download_path == str(fallback_dir)
        assert os.path.exists(downloader.download_path)

def test_downloader_primary_success(tmp_path):
    """Verify that downloader uses primary path if it is reachable and writable."""
    primary_dir = tmp_path / "nas_simulation"
    primary_dir.mkdir()
    
    with patch('src.downloader.settings') as mock_settings:
        mock_settings.download_dir = str(primary_dir)
        mock_settings.fallback_download_dir = "should_not_be_used"
        
        downloader = VideoDownloader()
        
        assert downloader.download_path == str(primary_dir)
        assert "nas_simulation" in downloader.download_path
