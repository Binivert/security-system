#!/usr/bin/env python3
"""Configuration settings."""

from pathlib import Path
from enum import Enum
import os


class AlertType(Enum):
    MOTION = "motion"
    PERSON = "person"
    ZONE_BREACH = "zone_breach"
    SYSTEM = "system"


class Sensitivity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Config:
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
    RECORDINGS_DIR = BASE_DIR / "recordings"
    SNAPSHOTS_DIR = BASE_DIR / "snapshots"
    ALERTS_DIR = BASE_DIR / "alerts"
    TRUSTED_FACES_DIR = BASE_DIR / "trusted_faces"
    FIXED_IMAGES_DIR = BASE_DIR / "fixed_images"  # Processed trusted faces database
    
    for d in [RECORDINGS_DIR, SNAPSHOTS_DIR, ALERTS_DIR, TRUSTED_FACES_DIR, FIXED_IMAGES_DIR]:
        d.mkdir(exist_ok=True)
    
    FRAME_WIDTH = 1280
    FRAME_HEIGHT = 720
    
    # YOLO detection thresholds per sensitivity
    YOLO_CONFIDENCE_HIGH = 0.25    # More sensitive - detect more
    YOLO_CONFIDENCE_MEDIUM = 0.40  # Balanced
    YOLO_CONFIDENCE_LOW = 0.60     # Less sensitive - only very confident
    
    # Default confidence
    YOLO_CONFIDENCE = YOLO_CONFIDENCE_MEDIUM
    
    # Skeleton detection thresholds
    SKELETON_CONFIDENCE_HIGH = 0.3
    SKELETON_CONFIDENCE_MEDIUM = 0.5
    SKELETON_CONFIDENCE_LOW = 0.7
    SKELETON_CONFIDENCE = SKELETON_CONFIDENCE_MEDIUM
    
    # Face recognition
    FACE_MATCH_TOLERANCE = 0.6
    FACE_DETECTION_SCALE = 0.25
    
    # Motion detection thresholds
    MOTION_THRESHOLD = 25
    MOTION_MIN_AREA = 500
    
    BREACH_PHOTO_INTERVAL = 180
    
    # Telegram credentials
    TELEGRAM_BOT_TOKEN = "8560050150:AAH4Dzk0TfE0xezzNsdZFhta1svOLPOvs4k"
    TELEGRAM_CHAT_ID = "7456977789"
    
    ALARM_FREQUENCY = 880
    
    # Auto-process interval for trusted faces (seconds)
    TRUSTED_FACES_CHECK_INTERVAL = 5
    
    def get_sensitivity_settings(self, sensitivity: Sensitivity) -> dict:
        """Get detection settings based on sensitivity level."""
        return {
            Sensitivity.LOW: {
                'yolo_confidence': 0.60,
                'skeleton_confidence': 0.7,
                'motion_threshold': 35,
                'motion_min_area': 1000
            },
            Sensitivity.MEDIUM: {
                'yolo_confidence': 0.40,
                'skeleton_confidence': 0.5,
                'motion_threshold': 25,
                'motion_min_area': 500
            },
            Sensitivity.HIGH: {
                'yolo_confidence': 0.25,
                'skeleton_confidence': 0.3,
                'motion_threshold': 15,
                'motion_min_area': 200
            }
        }.get(sensitivity, {
            'yolo_confidence': 0.40,
            'skeleton_confidence': 0.5,
            'motion_threshold': 25,
            'motion_min_area': 500
        })
