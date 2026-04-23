import unittest
import json
from unittest.mock import MagicMock, patch
from src.fetcher import VideoFetcher

class TestVideoFetcher(unittest.TestCase):
    @patch('src.fetcher.YouTubeClient')
    def test_fetch_daily_videos_selection(self, MockClient):
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

        # Dummy channels file content
        channels_data = {
            "channels": [
                {"id": "en_channel", "lang": "en"},
                {"id": "ja_channel", "lang": "ja"}
            ]
        }

        with patch('builtins.open', unittest.mock.mock_open(read_data=json.dumps(channels_data))):
            fetcher = VideoFetcher("fake_key", "fake_channels.json")
            selected = fetcher.fetch_daily_videos()

            self.assertIsNotNone(selected['en'])
            self.assertIsNotNone(selected['ja'])
            self.assertEqual(selected['en']['title'], 'EN Video')
            self.assertEqual(selected['ja']['title'], 'JA Video')

    @patch('src.fetcher.YouTubeClient')
    def test_fetch_daily_videos_empty(self, MockClient):
        mock_instance = MockClient.return_value
        mock_instance.get_recent_videos.return_value = []

        channels_data = {"channels": [{"id": "en_channel", "lang": "en"}]}

        with patch('builtins.open', unittest.mock.mock_open(read_data=json.dumps(channels_data))):
            fetcher = VideoFetcher("fake_key", "fake_channels.json")
            selected = fetcher.fetch_daily_videos()

            self.assertIsNone(selected['en'])
            self.assertIsNone(selected['ja'])

if __name__ == '__main__':
    unittest.main()
