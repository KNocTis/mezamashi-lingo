import os
import logging
import json
import shutil
from datetime import datetime, timedelta
from src.config import settings

class LoggerManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LoggerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, keep_logs_days=30):
        if not hasattr(self, 'initialized'):
            self.base_log_dir = settings.log_dir
            self.keep_logs_days = keep_logs_days
            self.start_datetime = datetime.now()
            self.start_time_prefix = self.start_datetime.strftime("%y%m%d-%H-%M")
            self.date_folder_name = self.start_datetime.strftime("%Y%m%d")
            self.current_log_dir = os.path.join(self.base_log_dir, self.date_folder_name)
            
            self._setup_directories()
            self._cleanup_old_logs()
            
            # Keep track of initialized loggers to avoid duplicate handlers
            self._loggers = {}
            self.initialized = True

    def _setup_directories(self):
        os.makedirs(self.current_log_dir, exist_ok=True)
        
        # Setup symlink to 'latest'
        latest_symlink = os.path.join(self.base_log_dir, 'latest')
        try:
            if os.path.exists(latest_symlink) or os.path.islink(latest_symlink):
                os.unlink(latest_symlink)
            os.symlink(self.date_folder_name, latest_symlink)
        except OSError:
            # Might fail on Windows without admin rights, or if there's a permission issue
            pass

    def _cleanup_old_logs(self):
        cutoff_date = self.start_datetime - timedelta(days=self.keep_logs_days)
        cutoff_folder = cutoff_date.strftime("%Y%m%d")
        
        try:
            if os.path.exists(self.base_log_dir):
                for item in os.listdir(self.base_log_dir):
                    item_path = os.path.join(self.base_log_dir, item)
                    # Check if it's a date folder (8 digits)
                    if os.path.isdir(item_path) and item.isdigit() and len(item) == 8:
                        if item < cutoff_folder:
                            shutil.rmtree(item_path, ignore_errors=True)
        except Exception:
            pass

    def _get_file_path(self, context, category, ext):
        filename = f"{self.start_time_prefix}-{context}-{category}.{ext}"
        return os.path.join(self.current_log_dir, filename)

    def get_main_logger(self, context="fetch", name=None):
        logger_name = name or f"main_{context}"
        if logger_name in self._loggers:
            return self._loggers[logger_name]
            
        logger = logging.getLogger(logger_name)
        
        # Clear existing handlers if any
        if logger.hasHandlers():
            logger.handlers.clear()
            
        logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
        
        log_file = self._get_file_path(context, "main", "log")
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        logger.propagate = False
        
        self._loggers[logger_name] = logger
        return logger

    def _append_jsonl(self, filepath, data):
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                json_str = json.dumps(data, ensure_ascii=False)
                f.write(json_str + '\n')
        except Exception as e:
            # Fallback to standard logging if JSONL fails
            fallback_logger = self.get_main_logger("system")
            fallback_logger.error(f"Failed to write to JSONL {filepath}: {e}")

    def _write_json(self, filepath, data):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            fallback_logger = self.get_main_logger("system")
            fallback_logger.error(f"Failed to write to JSON {filepath}: {e}")

    def log_youtube_api(self, endpoint, request_info, response_info, duration_ms, context="fetch"):
        filepath = self._get_file_path(context, "youtube", "jsonl")
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "endpoint": endpoint,
            "duration_ms": duration_ms,
            "request": request_info,
            "response": response_info
        }
        self._append_jsonl(filepath, log_entry)

    def log_llm_request(self, category, prompt, response, duration_ms, video_id):
        filepath = self._get_file_path(video_id, f"llm-{category}", "jsonl")
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "prompt": prompt,
            "response": response
        }
        self._append_jsonl(filepath, log_entry)

    def log_transcription_params(self, params, video_id):
        filepath = self._get_file_path(video_id, "transcription", "json")
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "parameters": params
        }
        self._write_json(filepath, log_entry)

# Global instance
logger_manager = LoggerManager()
