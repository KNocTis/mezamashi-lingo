import json
import logging
import litellm
from typing import Optional, List, Dict, Any
from .config import settings
from .models import VideoMetadata
from src.logger import logger_manager

logger = logger_manager.get_main_logger("fetch", __name__)

class LLMClient:
    def __init__(self, model: Optional[str] = None, api_base: Optional[str] = None, api_key: Optional[str] = None, 
                 fallback_model: Optional[str] = None, fallback_api_key: Optional[str] = None, fallback_api_base: Optional[str] = None) -> None:
        self.model = model or settings.llm_model
        self.api_base = api_base or settings.llm_api_base
        self.api_key = api_key or settings.llm_api_key
        self.fallback_model = fallback_model or settings.fallback_llm_model
        self.fallback_api_key = fallback_api_key or settings.fallback_llm_api_key
        self.fallback_api_base = fallback_api_base or settings.fallback_llm_api_base

    def completion(self, messages: List[Dict[str, str]], log_category: str = "general", video_id: str = "fetch", **kwargs: Any) -> str:
        """Generic completion wrapper with automatic failover support."""
        import time
        start_time = time.time()
        result_content = None
        
        try:
            # Attempt 1: Primary Model (Local or Preferred)
            call_kwargs = kwargs.copy()
            if self.api_base:
                call_kwargs['api_base'] = self.api_base
            if self.api_key:
                call_kwargs['api_key'] = self.api_key
            
            # Apply advanced settings
            if settings.llm_max_tokens:
                call_kwargs['max_tokens'] = settings.llm_max_tokens
            
            if settings.llm_extra_params:
                try:
                    extra = json.loads(settings.llm_extra_params)
                    call_kwargs.update(extra)
                except Exception as e:
                    logger.warning(f"Failed to parse LLM_EXTRA_PARAMS: {e}")
                
            result_content = litellm.completion(
                model=self.model,
                messages=messages,
                num_retries=1, # Low retries for primary to fail fast to fallback
                **call_kwargs
            ).choices[0].message.content
            return result_content
            
        except Exception as e:
            # Attempt 2: Fallback Model (Cloud) if primary fails
            if self.fallback_model:
                logger.warning(f"Primary LLM ({self.model}) failed. Switching to fallback: {self.fallback_model}. Error: {e}")
                try:
                    fallback_kwargs = kwargs.copy()
                    if self.fallback_api_base:
                        fallback_kwargs['api_base'] = self.fallback_api_base
                        
                    result_content = litellm.completion(
                        model=self.fallback_model,
                        messages=messages,
                        api_key=self.fallback_api_key,
                        num_retries=3,
                        **fallback_kwargs
                    ).choices[0].message.content
                    return result_content
                except Exception as fallback_e:
                    logger.error(f"Fallback LLM also failed: {fallback_e}")
                    raise fallback_e
            else:
                logger.error(f"LLM call failed and no fallback configured: {e}")
                raise e
        finally:
            if result_content is not None:
                duration_ms = int((time.time() - start_time) * 1000)
                logger_manager.log_llm_request(log_category, messages, result_content, duration_ms, video_id)

    def select_best_video(self, language: str, videos: List[VideoMetadata], recent_titles: Optional[List[str]] = None) -> Optional[VideoMetadata]:
        """
        Sends a list of videos to LLM and asks it to select the best one for language learning.
        Includes recently seen titles to ensure topic variety.
        """
        if not videos:
            return None
        
        if len(videos) == 1:
            return videos[0]

        # Prepare the list of videos for the prompt
        video_list_str = ""
        for i, v in enumerate(videos):
            duration_min = round(v.duration_sec / 60, 1)
            video_list_str += f"{i}. Title: {v.title} | Duration: {duration_min} min\n"

        # Prepare recent history context
        history_context = ""
        if recent_titles:
            history_context = "\nRecently studied topics (titles):\n- " + "\n- ".join(recent_titles)

        prompt = f"""
You are an expert language teacher specializing in {language}. 
Your task is to select the absolute BEST video for a language learner from the list below.

Criteria for selection:
1. Educational Value: Prefer videos with clear, standard speech (news, documentaries, educational content).
2. Topic Variety: CRITICAL - Avoid videos that cover the same topics as the recently studied titles listed below. We want a fresh subject every day.
3. Duration: Prefer videos around 3-5 minutes.
4. Content: Prefer titles that suggest a narrative or clear topic.
{history_context}

Videos:
{video_list_str}

Response format:
Respond ONLY with a JSON object containing the index of the selected video and a brief one-sentence reason highlighting why this topic is a good change of pace.
Example: {{"index": 0, "reason": "This is a travel documentary, which provides a great contrast to the political news from yesterday."}}
"""

        try:
            content = self.completion([
                {
                    "role": "user",
                    "content": prompt,
                }
            ], log_category="selection", video_id="fetch")

            result = json.loads(content)
            selected_index = int(result.get("index", 0))
            reason = result.get("reason", "No reason provided.")
            
            logger.info(f"LLM selected {language} video index {selected_index}. Reason: {reason}")
            
            if 0 <= selected_index < len(videos):
                selected_video = videos[selected_index]
                selected_video.llm_reason = reason
                return selected_video
            
            return videos[0]
        except Exception as e:
            logger.error(f"Error during LLM selection: {e}")
            return videos[0] # Fallback to first video
