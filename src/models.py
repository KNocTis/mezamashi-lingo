from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class ChannelConfig(BaseModel):
    id: str
    name: str
    lang: str

class VideoMetadata(BaseModel):
    video_id: str
    title: str
    duration_sec: int = 0
    lang: Optional[str] = None
    published_at: Optional[str] = None
    thumbnail_url: Optional[str] = None
    llm_reason: Optional[str] = None
    local_path: Optional[str] = None

class TranscriptionSegment(BaseModel):
    start: float
    end: float
    text: str
    translated_text: Optional[str] = None

class GlossaryTerm(BaseModel):
    term: str
    pronunciation: Optional[str] = None
    translation: str
    explanation: str

class HistoryEntry(VideoMetadata):
    selected_at: datetime = Field(default_factory=datetime.now)

    @property
    def id(self) -> str:
        return self.video_id

class ProcessingState(BaseModel):
    selected_videos: List[VideoMetadata] = []
    downloaded_files: List[VideoMetadata] = []
    transcription_results: List[VideoMetadata] = [] # Using VideoMetadata to track paths
