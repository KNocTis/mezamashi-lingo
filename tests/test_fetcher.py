import unittest
import json
from unittest.mock import MagicMock, patch
from src.fetcher import VideoFetcher
from src.models import ChannelConfig, HistoryEntry

class TestVideoFetcher(unittest.TestCase):
    @patch('src.fetcher.Repository')
    @patch('src.fetcher.YouTubeClient')
    def test_fetch_daily_videos_selection(self, MockClient, MockRepository):
        # Setup mock client behavior
        mock_instance = MockClient.return_value
        
        # Mock get_uploads_playlist_id
        mock_instance.get_uploads_playlist_id.side_effect = lambda cid: f"playlist_{cid}"
        
        # Mock get_recent_videos with dummy data
        def mock_get_recent(pid, hours=24):
            if "en" in pid:
                return [{'title': 'EN Video', 'url': 'url_en', 'published_at': 'date', 'video_id': 'id_en'}]
            if "ja" in pid:
                return [{'title': 'JA Video', 'url': 'url_ja', 'published_at': 'date', 'video_id': 'id_ja'}]
            return []
        
        mock_instance.get_recent_videos.side_effect = mock_get_recent
        mock_instance.get_video_durations.return_value = {'id_en': 100, 'id_ja': 200}
        mock_instance.api_key = "fake_key"

        MockRepository.load_channels.return_value = [
            ChannelConfig(id="en_channel", name="EN Channel", lang="en"),
            ChannelConfig(id="ja_channel", name="JA Channel", lang="ja")
        ]
        MockRepository.load_history.return_value = []
        MockRepository.load_raw_selection.return_value = []

        fetcher = VideoFetcher(mock_instance)
        selected = fetcher.fetch_daily_videos()

        self.assertIsNotNone(selected['en'])
        self.assertIsNotNone(selected['ja'])
        self.assertEqual(selected['en'].title, 'EN Video')
        self.assertEqual(selected['ja'].title, 'JA Video')

    @patch('src.fetcher.Repository')
    @patch('src.fetcher.YouTubeClient')
    def test_fetch_daily_videos_empty(self, MockClient, MockRepository):
        mock_instance = MockClient.return_value
        mock_instance.get_recent_videos.return_value = []
        mock_instance.api_key = "fake_key"

        MockRepository.load_channels.return_value = [
            ChannelConfig(id="en_channel", name="EN Channel", lang="en")
        ]
        MockRepository.load_history.return_value = []
        MockRepository.load_raw_selection.return_value = []

        fetcher = VideoFetcher(mock_instance)
        selected = fetcher.fetch_daily_videos()

        self.assertIsNone(selected.get('en'))
        self.assertIsNone(selected.get('ja'))

    @patch('src.fetcher.Repository')
    @patch('src.fetcher.YouTubeClient')
    def test_fetch_daily_videos_with_existing_selection(self, MockClient, MockRepository):
        mock_instance = MockClient.return_value
        mock_instance.api_key = "fake_key"
        
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        MockRepository.load_channels.return_value = [
            ChannelConfig(id="en_channel", name="EN Channel", lang="en"),
            ChannelConfig(id="ja_channel", name="JA Channel", lang="ja")
        ]
        
        # 'en' was already selected today
        MockRepository.load_history.return_value = [
            HistoryEntry(video_id="id_en_old", title="EN Video Old", lang="en", duration_sec=100)
        ]
        
        MockRepository.load_raw_selection.return_value = [
            {"video_id": "id_en_old", "date_picked": today_str}
        ]
        
        def mock_get_recent(pid, hours=24):
            if "ja" in pid:
                return [{'title': 'JA Video New', 'url': 'url_ja', 'published_at': 'date', 'video_id': 'id_ja_new'}]
            return []
        
        mock_instance.get_uploads_playlist_id.side_effect = lambda cid: f"playlist_{cid}"
        mock_instance.get_recent_videos.side_effect = mock_get_recent
        mock_instance.get_video_durations.return_value = {'id_ja_new': 200}
        
        fetcher = VideoFetcher(mock_instance)
        selected = fetcher.fetch_daily_videos()
        
        # 'en' should come from existing selection
        self.assertIsNotNone(selected['en'])
        self.assertEqual(selected['en'].title, "EN Video Old")
        
        # 'ja' should be newly fetched
        self.assertIsNotNone(selected['ja'])
        self.assertEqual(selected['ja'].title, "JA Video New")
        
        # Verify get_recent_videos was only called for 'ja'
        mock_instance.get_recent_videos.assert_called_once_with('playlist_ja_channel')

    @patch('src.fetcher.Repository')
    @patch('src.fetcher.YouTubeClient')
    def test_fetch_daily_videos_force_fetch(self, MockClient, MockRepository):
        mock_instance = MockClient.return_value
        mock_instance.api_key = "fake_key"
        
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        MockRepository.load_channels.return_value = [
            ChannelConfig(id="en_channel", name="EN Channel", lang="en"),
            ChannelConfig(id="ja_channel", name="JA Channel", lang="ja")
        ]
        
        # Both already selected today
        MockRepository.load_history.return_value = [
            HistoryEntry(video_id="id_en_old", title="Old EN Video", lang="en", duration_sec=100),
            HistoryEntry(video_id="id_ja_old", title="Old JA Video", lang="ja", duration_sec=200)
        ]
        
        MockRepository.load_raw_selection.return_value = [
            {"video_id": "id_en_old", "date_picked": today_str},
            {"video_id": "id_ja_old", "date_picked": today_str}
        ]
        
        def mock_get_recent(pid, hours=24):
            if "en" in pid:
                return [{'title': 'New EN Video', 'url': 'url_en_new', 'published_at': 'date', 'video_id': 'id_en_new'}]
            if "ja" in pid:
                return [{'title': 'New JA Video', 'url': 'url_ja_new', 'published_at': 'date', 'video_id': 'id_ja_new'}]
            return []
            
        mock_instance.get_uploads_playlist_id.side_effect = lambda cid: f"playlist_{cid}"
        mock_instance.get_recent_videos.side_effect = mock_get_recent
        mock_instance.get_video_durations.return_value = {'id_en_new': 150, 'id_ja_new': 250}
        
        fetcher = VideoFetcher(mock_instance)
        # Calling with force=True to bypass existing selection
        selected = fetcher.fetch_daily_videos(force=True)
        
        # Should get new videos
        self.assertEqual(selected['en'].title, "New EN Video")
        self.assertEqual(selected['ja'].title, "New JA Video")
        
        # Verify get_recent_videos was called twice
        self.assertEqual(mock_instance.get_recent_videos.call_count, 2)

if __name__ == '__main__':
    unittest.main()
