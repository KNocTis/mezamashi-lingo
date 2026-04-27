import os
import pytest
import json
import subprocess
from src.youtube_client import YouTubeClient
from src.llm_client import LLMClient
from src.transcriber import VideoTranscriber
from src.translator import SubtitleTranslator
from src.models import TranscriptionSegment, VideoMetadata

# Setup paths
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TEST_VIDEO = os.path.join(FIXTURES_DIR, "test_video.mp4")
TEST_AUDIO = os.path.join(FIXTURES_DIR, "test_audio.wav")
TEST_TRANSCRIPTION = os.path.join(FIXTURES_DIR, "test_transcription.json")

def get_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

@pytest.fixture
def youtube_client():
    return YouTubeClient()

@pytest.fixture
def llm_client():
    from src.config import settings
    # No token limit to avoid truncation, but still disable reasoning output
    settings.llm_max_tokens = None 
    settings.llm_extra_params = '{"include_reasoning": false, "temperature": 0}'
    return LLMClient()

@pytest.fixture
def transcriber():
    return VideoTranscriber(model_name="base") # Use small model for faster testing

@pytest.fixture
def translator(llm_client):
    return SubtitleTranslator(llm_client)

def test_youtube_api_success(youtube_client):
    """1. Make sure that we can call YouTube APIs successfully. We should get at least one video."""
    channel_id = "UC6AG81pAkf6Lbi_1VC5NmPA" # TBS NEWS DIG
    playlist_id = youtube_client.get_uploads_playlist_id(channel_id)
    assert playlist_id is not None
    
    # Fetch videos from last 7 days to ensure we get something
    videos = youtube_client.get_recent_videos(playlist_id, hours=168)
    assert len(videos) >= 1
    assert "title" in videos[0]
    assert "video_id" in videos[0]

def test_llm_completion_success(llm_client):
    """2. we can successfully initiate our LM client. and do some very basic Completion."""
    response = llm_client.completion([{"role": "user", "content": "Say 'Mezamashi Lingo' and nothing else."}])
    assert "Mezamashi Lingo" in response

def test_audio_separation_success(transcriber):
    """3. we should be able to successfully separate auto track from a video."""
    # We use separate_vocals which internally uses demucs
    # For testing, we'll check if the output file is created and duration matches
    vocals_path = transcriber.separate_vocals(TEST_VIDEO, vocals_dir=OUTPUT_DIR)
    
    assert os.path.exists(vocals_path)
    assert vocals_path.endswith("_vocals.wav")
    
    video_duration = get_duration(TEST_VIDEO)
    audio_duration = get_duration(vocals_path)
    
    # Match within 1 second
    assert abs(video_duration - audio_duration) < 1.0

def test_transcription_success(transcriber):
    """4. we should be able to transcribe from the audio track."""
    # Use the prepared audio fixture for speed and reliability
    segments = transcriber.transcribe(TEST_AUDIO, language="ja", use_vocal_separation=False)
    
    assert len(segments) > 0
    assert isinstance(segments[0], TranscriptionSegment)
    assert segments[0].text != ""

def test_translation_success(translator):
    """5. we can successfully get the translation."""
    # Load the 50+ lines transcription fixture
    with open(TEST_TRANSCRIPTION, 'r', encoding='utf-8') as f:
        data = json.load(f)
        segments = [TranscriptionSegment(**s) for s in data]
    
    # Clear any existing translations to force fresh LLM calls
    for s in segments:
        s.translated_text = None
    
    # Set batch size to 5 to force two batches for our 10-line fixture
    translator.batch_size = 5
    
    translated_chunks = list(translator.translate_segments(segments, source_lang="ja"))
    
    # Flatten the results
    all_translated = [seg for chunk in translated_chunks for seg in chunk]
    
    assert len(all_translated) == len(segments)
    
    # Stricter checks:
    # 1. At least 80% should be translated
    translated_count = sum(1 for s in all_translated if s.translated_text and s.translated_text != s.text)
    assert translated_count > len(segments) * 0.8
    
    # 2. Check for Chinese characters in translated text
    import re
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
    for seg in all_translated[:10]: # Check first 10
        if seg.translated_text and seg.translated_text != seg.text:
            assert chinese_pattern.search(seg.translated_text), f"Translation should contain Chinese: {seg.translated_text}"

def test_vocabulary_extraction_success(translator):
    """6. we can successfully get the vocabulary list."""
    with open(TEST_TRANSCRIPTION, 'r', encoding='utf-8') as f:
        data = json.load(f)
        segments = [TranscriptionSegment(**s) for s in data]
    
    glossary = translator.build_glossary(segments, source_lang="ja")
    
    assert len(glossary) > 0
    
    import re
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
    
    for term in glossary:
        assert term.term != "", "Term should not be empty"
        assert term.translation != "", f"Translation for {term.term} should not be empty"
        assert term.explanation != "", f"Explanation for {term.term} should not be empty"
        
        # Ensure translation and explanation contain Chinese characters (since target is Simplified Chinese)
        assert chinese_pattern.search(term.translation), f"Translation '{term.translation}' should contain Chinese"
        assert chinese_pattern.search(term.explanation), f"Explanation '{term.explanation}' should contain Chinese"
    
    # Check if we can save it to a file (simulating the actual app flow)
    vocab_path = os.path.join(OUTPUT_DIR, "test_vocab.json")
    with open(vocab_path, 'w', encoding='utf-8') as f:
        json_data = [g.model_dump() for g in glossary]
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    assert os.path.exists(vocab_path)
    with open(vocab_path, 'r', encoding='utf-8') as f:
        saved_data = json.load(f)
        assert len(saved_data) == len(glossary)
