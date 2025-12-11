#!/usr/bin/env python3
"""
Advanced Security System with YOLOv8 Detection
==============================================

Features:
- YOLOv8 person detection (accurate, no false positives)
- Adjustable sensitivity (Low/Medium/High)
- Face recognition for trusted persons
- Motion detection with heat map
- Multi-zone breach detection
- Telegram controls with inline buttons
- Video playback support
- Night vision mode

Requirements:
    pip install ultralytics opencv-python PyQt6 face-recognition mediapipe

Usage:
    python main.py
"""
import torch  
import sys
import os

# Suppress TensorFlow and other warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS'] = '0'

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Security System")
    app.setStyle('Fusion')
    
    # Check for YOLO
    try:
        from ultralytics import YOLO
        print("✓ YOLOv8 available")
    except ImportError:
        print("✗ YOLOv8 not installed. Run: pip install ultralytics")
        print("  Detection will not work without it.")
    
    from gui import SecuritySystemWindow
    
    window = SecuritySystemWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
