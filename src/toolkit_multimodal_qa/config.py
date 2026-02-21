"""Configuration management for Multimodal Dataset QA"""
import os
from pathlib import Path


class Config:
    """Configuration settings"""
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    CHECK_IMAGE_QUALITY: bool = os.getenv("CHECK_IMAGE_QUALITY", "true").lower() == "true"
    CHECK_TEXT_QUALITY: bool = os.getenv("CHECK_TEXT_QUALITY", "true").lower() == "true"
    CHECK_CONSISTENCY: bool = os.getenv("CHECK_CONSISTENCY", "true").lower() == "true"
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "/app/reports"))
    
    @classmethod
    def validate(cls) -> None:
        """Validate configuration"""
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if cls.LOG_LEVEL.upper() not in valid_log_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_log_levels}")


Config.validate()

