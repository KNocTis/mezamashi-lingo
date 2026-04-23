import os
import stable_whisper
import logging
import json
import torch
import shutil
import subprocess

logger = logging.getLogger(__name__)

from .models import TranscriptionSegment
from .config import settings
from typing import List, Optional

class VideoTranscriber:
    def __init__(self, model_name='large-v3-turbo'):
        # Check if we are on Apple Silicon to use MLX optimization
        self.is_arm64 = os.uname().machine == 'arm64'
        self.model_name = model_name
        self.model = None
        self.separator = None

    def _load_model(self):
        if self.model is None:
            logger.info(f"Loading Whisper model: {self.model_name} (MLX: {self.is_arm64})")
            if self.is_arm64:
                self.model = stable_whisper.load_mlx_whisper(self.model_name)
            else:
                self.model = stable_whisper.load_model(self.model_name)
        return self.model

    def separate_vocals(self, file_path, vocals_dir=None):
        """Separates vocals using demucs. Skips if already exists."""
        vocals_dir = vocals_dir or settings.vocals_dir
        os.makedirs(vocals_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Demucs default output: output_dir/model_name/input_name/vocals.wav
        model_name = "htdemucs"
        expected_output_dir = os.path.join(vocals_dir, model_name, base_name)
        expected_output = os.path.join(expected_output_dir, "vocals.wav")
        
        # Target path we want to use
        final_vocals_path = os.path.join(vocals_dir, f"{base_name}_vocals.wav")

        if os.path.exists(final_vocals_path):
            logger.info(f"Skipping vocal separation, file already exists: {final_vocals_path}")
            return final_vocals_path

        logger.info(f"Starting vocal separation for: {file_path}")
        try:
            # We use subprocess to run demucs to avoid SystemExit issues and keep a clean environment
            # Use the same python as currently running to ensure venv and demucs availability
            import sys
            cmd = [
                sys.executable, "-m", "demucs.separate",
                "-n", model_name,
                "--two-stems", "vocals",
                "-o", vocals_dir,
                file_path
            ]
            
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Demucs failed with return code {result.returncode}")
                logger.error(f"Demucs stderr: {result.stderr}")
                return file_path

            # Search for the output file
            # Sometimes demucs might use a slightly different folder name if there are special characters
            if not os.path.exists(expected_output):
                logger.warning(f"Expected output not found at {expected_output}. Searching...")
                # Search recursively for vocals.wav in vocals_dir/model_name
                found = False
                for root, dirs, files in os.walk(os.path.join(vocals_dir, model_name)):
                    if "vocals.wav" in files:
                        # Check if this folder seems related to our base_name
                        if base_name in root:
                            expected_output = os.path.join(root, "vocals.wav")
                            expected_output_dir = root
                            found = True
                            break
                if not found:
                    logger.error("Could not find vocals.wav in demucs output directory.")
                    return file_path

            # Move to the flatter structure we prefer
            if os.path.exists(final_vocals_path):
                os.remove(final_vocals_path)
            
            shutil.move(expected_output, final_vocals_path)
            
            # Cleanup the empty demucs folder structure (carefully)
            try:
                shutil.rmtree(expected_output_dir)
                # Also try to remove the model folder if it's empty
                model_dir = os.path.join(vocals_dir, model_name)
                if not os.listdir(model_dir):
                    os.rmdir(model_dir)
            except Exception as e:
                logger.warning(f"Cleanup of demucs temp folders failed: {e}")
                
            logger.info(f"Vocal separation completed: {final_vocals_path}")
            return final_vocals_path
                
        except Exception as e:
            logger.error(f"Vocal separation failed: {e}. Falling back to original file.")
            import traceback
            logger.error(traceback.format_exc())
            return file_path

    def transcribe(self, file_path, language=None, use_vocal_separation=True, output_srt=True) -> List[TranscriptionSegment]:
        """Transcribes a video/audio file, saves to SRT/JSON, and returns the segments."""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return []

        # Step 1: Vocal Separation
        audio_to_transcribe = file_path
        if use_vocal_separation:
            audio_to_transcribe = self.separate_vocals(file_path)

        model = self._load_model()
        logger.info(f"Starting transcription for: {audio_to_transcribe}")
        
        # Initial transcription
        result = model.transcribe(audio_to_transcribe, language=language)
        
        # --- Smart Segmentation Logic ---
        logger.info(f"Applying smart segmentation for {language}...")
        
        # 1. Basic regrouping to join word-level fragments
        result.regroup()
        
        if language == 'en':
            # 2. Split by strong punctuation (End of sentence)
            result.split_by_punctuation([('.', ' '), ('? ', ' '), ('! ', ' ')])
            
            # 3. Split by secondary punctuation if the segment is still long (Commas, etc.)
            result.split_by_punctuation([(',', ' '), ('; ', ' '), (': ', ' '), (' - ', ' ')])
            
            # 4. Split by natural pauses in speech (Gaps > 0.4s)
            result.split_by_gap(0.4)
            
            # 5. Final safety split: Force break if line exceeds study-friendly length
            result.split_by_length(max_chars=50, max_words=12)
            
            # 6. Final cleanup: Merge tiny fragments that were split too aggressively
            result.merge_by_gap(0.15)
            
        elif language == 'ja':
            # Japanese usually has shorter lines visually due to character density
            result.split_by_punctuation([('。', ''), ('？', ''), ('！', ''), ('、', '')])
            result.split_by_gap(0.5)
            result.split_by_length(max_chars=20)
        else:
            # Default for other languages
            result.split_by_punctuation([('.', ' '), ('? ', ' '), ('! ', ' ')])
            result.split_by_length(max_chars=50)

        # Step 2: Save as SRT if requested
        if output_srt:
            srt_path = os.path.splitext(file_path)[0] + ".srt"
            result.to_srt_vtt(srt_path, word_level=False)
            logger.info(f"SRT saved to: {srt_path}")

        # Step 3: Convert result to segments list
        segments = []
        for segment in result.segments:
            segments.append(TranscriptionSegment(
                start=round(segment.start, 3),
                end=round(segment.end, 3),
                text=segment.text.strip()
            ))
        
        return segments

    def save_transcription(self, segments: List[TranscriptionSegment], output_path):
        """Saves the transcription segments to a JSON file."""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json_data = [s.model_dump(mode='json') for s in segments]
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Transcription saved to: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save transcription: {e}")
            return False
