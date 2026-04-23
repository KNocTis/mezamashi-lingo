import os
import re
import logging
import json
import time
from src.llm_client import LLMClient

logger = logging.getLogger(__name__)

from .llm_client import LLMClient
from .models import TranscriptionSegment, GlossaryTerm
from .config import settings
from typing import List, Optional, Generator

class SubtitleTranslator:
    def __init__(self, llm_client: LLMClient, target_lang='Simplified Chinese'):
        self.llm_client = llm_client
        self.target_lang = target_lang
        self.batch_size = settings.translation_batch_size

    def _get_full_lang_name(self, lang_code):
        mapping = {
            'en': 'English',
            'ja': 'Japanese',
            'chs': 'Simplified Chinese',
            'zh': 'Simplified Chinese'
        }
        return mapping.get(lang_code.lower(), lang_code)

    def _get_system_prompt(self, source_lang):
        source_name = self._get_full_lang_name(source_lang)
        return f"""Act as a professional 'Subtitle Translator'. Your goal is to translate {source_name} subtitles into {self.target_lang}.
Rules:
1. Terminology Consistency: Keep names and technical terms consistent. Use the provided Glossary!
2. Technical Integrity: Use the EXACT format: [index] Translated text.
3. Natural Output: Ensure standard punctuation and NO spaces between Chinese characters if the target is Chinese.
4. No Truncation: Translate every single block provided. Do not skip any lines.
5. Context: Use the provided 'Look-back Context' to maintain tone and terminology.
6. NO extra commentary. Just the translated list."""

    def _clean_chinese_spacing(self, text):
        """Removes spaces between Chinese characters."""
        # Remove space between two Chinese characters
        text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', text)
        # Remove space before particles
        text = re.sub(r'([\u4e00-\u9fff])\s+([的了吧呢嘛呀吗])', r'\1\2', text)
        return text

    def _extract_json(self, text):
        """Extracts JSON from a string that might contain markdown blocks."""
        if not text:
            return None
        
        # Try to find JSON block
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            # Try to find first [ or { and last ] or }
            start_idx = text.find('{')
            start_idx_bracket = text.find('[')
            
            if start_idx == -1 or (start_idx_bracket != -1 and start_idx_bracket < start_idx):
                start_idx = start_idx_bracket
                
            end_idx = text.rfind('}')
            end_idx_bracket = text.rfind(']')
            
            if end_idx == -1 or (end_idx_bracket != -1 and end_idx_bracket > end_idx):
                end_idx = end_idx_bracket
                
            if start_idx != -1 and end_idx != -1:
                text = text[start_idx:end_idx+1]
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def build_glossary(self, segments: List[TranscriptionSegment], source_lang) -> List[GlossaryTerm]:
        """Identifies key/difficult vocabulary before translation to ensure consistency."""
        source_name = self._get_full_lang_name(source_lang)
        logger.info(f"Building glossary for {source_name} segments...")
        
        # Take a sample of the text (first 100 segments) to identify key terms
        sample_text = "\n".join([s.text for s in segments[:100]])
        
        system_prompt = f"""You are a professional language teacher specializing in {source_name} and {self.target_lang}.
Your task is to analyze a transcript and identify the most important vocabulary for a language learner."""

        user_prompt = f"""Analyze the following {source_name} transcript and identify the top 15 key vocabulary terms, 
idioms, or technical terms that are essential for a language learner to understand this specific topic.

For each term, you MUST provide:
1. 'term': The original {source_name} term.
2. 'translation': The most accurate {self.target_lang} translation for THIS specific context.
3. 'explanation': A brief one-sentence explanation in {self.target_lang} explaining the term's meaning in this context.

CRITICAL: The 'translation' and 'explanation' fields MUST be written in {self.target_lang}.

Response format: Respond ONLY with a JSON list of objects under a "vocabulary" key.
Transcript:
{sample_text}
"""
        try:
            response = self.llm_client.completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            data = self._extract_json(response)
            if data is None:
                logger.error(f"Failed to parse glossary JSON from response: {response[:100]}...")
                return []

            if isinstance(data, dict):
                for key in ['vocabulary', 'terms', 'glossary']:
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
            
            if not isinstance(data, list):
                logger.error(f"Unexpected glossary format: {type(data)}")
                return []
            
            final_glossary = []
            for item in data:
                if isinstance(item, dict) and item.get('term'):
                    final_glossary.append(GlossaryTerm(
                        term=item.get('term'),
                        translation=item.get('translation', ''),
                        explanation=item.get('explanation', '')
                    ))
            
            return final_glossary
        except Exception as e:
            logger.error(f"Failed to build glossary: {e}")
            return []

    def translate_segments(self, segments: List[TranscriptionSegment], source_lang='en', glossary: List[GlossaryTerm] = None) -> Generator[List[TranscriptionSegment], None, None]:
        """Generator that yields translated chunks for incremental saving."""
        lookback_context = []
        
        # Format glossary for the prompt
        glossary_str = "None"
        if glossary:
            glossary_str = "\n".join([f"- {g.term}: {g.translation} ({g.explanation})" for g in glossary])

        # Chunking Logic
        total_chunks = (len(segments) + self.batch_size - 1) // self.batch_size
        logger.info(f"Starting translation: {len(segments)} segments in {total_chunks} chunks.")

        for i in range(0, len(segments), self.batch_size):
            chunk = segments[i:i + self.batch_size]
            chunk_num = (i // self.batch_size) + 1
            total_segments_in_chunk = len(chunk)

            # --- SMART SKIP CHECK ---
            already_translated = True
            for seg in chunk:
                if not seg.translated_text or seg.translated_text == seg.text:
                    already_translated = False
                    break
            
            if already_translated:
                logger.info(f"Chunk {chunk_num}/{total_chunks} already translated. Skipping.")
                for seg in chunk:
                    lookback_context.append(f"[{segments.index(seg)+1}] {seg.translated_text}")
                yield chunk
                continue
            
            # Prepare the batch text: [index] text
            batch_text = "\n".join([f"[{j+1+i}] {s.text}" for j, s in enumerate(chunk)])
            
            # Prepare lookback context (last 3 translated lines)
            context_str = "\n".join(lookback_context[-3:]) if lookback_context else "None"
            
            source_name = self._get_full_lang_name(source_lang)
            prompt = f"Mandatory Glossary (Use these EXACT translations!):\n{glossary_str}\n\n"
            prompt += f"Look-back Context (last few lines for tone):\n{context_str}\n\n"
            prompt += f"Translate these {source_name} segments into {self.target_lang}. \n"
            prompt += "CRITICAL: You MUST provide a translation for EVERY index. Do not merge lines. Do not skip indices. \n"
            prompt += f"Keep the [index] format exactly:\n{batch_text}"
            
            logger.info(f"Translating chunk {chunk_num}/{total_chunks}...")
            
            chunk_results = []
            success = False
            
            # Internal retry loop
            for attempt in range(2):
                try:
                    response = self.llm_client.completion(
                        messages=[
                            {"role": "system", "content": self._get_system_prompt(source_lang)},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    
                    translated_chunk_map = {}
                    matches = re.findall(r'[\[\(]?(\d+)[\]\):]\s*(.*)', response)
                    for idx_str, text in matches:
                        idx = int(idx_str)
                        cleaned_text = self._clean_chinese_spacing(text.strip())
                        translated_chunk_map[idx] = cleaned_text
                    
                    found_count = sum(1 for j in range(total_segments_in_chunk) if (i + j + 1) in translated_chunk_map)
                    
                    if found_count >= total_segments_in_chunk * 0.95:
                        success = True
                        for j, seg in enumerate(chunk):
                            idx = i + j + 1
                            trans_text = translated_chunk_map.get(idx, seg.text)
                            seg.translated_text = trans_text
                            chunk_results.append(seg)
                            lookback_context.append(f"[{idx}] {trans_text}")
                        break
                    else:
                        logger.warning(f"Chunk {chunk_num} parsing glitch (found {found_count}/{total_segments_in_chunk}).")
                
                except Exception as e:
                    logger.error(f"Error in translation attempt {attempt+1}: {e}")
                    time.sleep(2)

            if success:
                yield chunk_results
            else:
                logger.error(f"Chunk {chunk_num} failed. Falling back.")
                for seg in chunk:
                    seg.translated_text = seg.text
                yield chunk
            
            time.sleep(1)

    def save_bilingual_srt(self, segments: List[TranscriptionSegment], output_path):
        """Saves a bilingual SRT file: [Original]\n[Translated]"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for i, seg in enumerate(segments):
                    idx = i + 1
                    start = self._format_timestamp(seg.start)
                    end = self._format_timestamp(seg.end)
                    original = seg.text
                    translated = seg.translated_text or ""
                    
                    f.write(f"{idx}\n{start} --> {end}\n{original}\n{translated}\n\n")
            logger.info(f"Bilingual SRT saved to: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save bilingual SRT: {e}")
            return False

    def _format_timestamp(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        ms = int((s - int(s)) * 1000)
        return f"{h:02d}:{m:02d}:{int(s):02d},{ms:03d}"
