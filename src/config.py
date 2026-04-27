import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # API Keys
    youtube_api_key: str
    llm_model: str = "groq/llama-3.3-70b-versatile"
    llm_api_base: Optional[str] = None
    llm_api_key: Optional[str] = None
    
    fallback_llm_model: Optional[str] = None
    fallback_llm_api_key: Optional[str] = None
    fallback_llm_api_base: Optional[str] = None
    
    # LLM Advanced Settings
    llm_max_tokens: Optional[int] = None
    llm_extra_params: Optional[str] = None # JSON string for extra parameters
    
    # Paths
    log_dir: str = "logs"
    download_dir: str = "downloads"
    fallback_download_dir: str = "downloads" # Local fallback if NAS is down
    vocals_dir: str = "downloads/vocals"
    channels_file: str = "channels.json"
    history_file: str = "history.json"
    selection_file: str = "latest_selection.json"
    templates_dir: str = "templates"
    
    # App Settings
    log_level: str = "INFO"
    translation_batch_size: int = 25
    max_video_duration_sec: int = 600 # 10 minutes
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Singleton instance
settings = Settings()
