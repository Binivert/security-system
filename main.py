#!/usr/bin/env python3
"""
Advanced Security System
========================
"""

import sys
import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS'] = '0'

from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient


def check_gpu() -> bool:
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✓ GPU: {torch.cuda.get_device_name(0)}")
            return True
        print("✗ No GPU, using CPU")
        return False
    except ImportError:
        print("✗ PyTorch not installed")
        return False


def check_dependencies():
    print("\n" + "="*50)
    print("🛡️  SECURITY SYSTEM")
    print("="*50 + "\n")
    
    try:
        from ultralytics import YOLO
        print("✓ YOLOv8")
    except ImportError:
        print("✗ YOLOv8 - Run: pip install ultralytics")
    
    try:
        import face_recognition
        print("✓ Face Recognition")
    except ImportError:
        print("○ Face Recognition (optional)")
    
    try:
        import mediapipe
        print("✓ MediaPipe")
    except ImportError:
        print("○ MediaPipe (optional)")
    
    print("")
    has_gpu = check_gpu()
    print("\n" + "="*50 + "\n")
    return has_gpu


class AnimatedSplash(QSplashScreen):
    def __init__(self):
        pixmap = QPixmap(500, 320)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        gradient = QLinearGradient(0, 0, 500, 320)
        gradient.setColorAt(0, QColor(5, 5, 25))
        gradient.setColorAt(0.5, QColor(10, 10, 40))
        gradient.setColorAt(1, QColor(5, 5, 25))
        painter.fillRect(0, 0, 500, 320, gradient)
        
        painter.setPen(QColor(0, 255, 255))
        painter.drawRoundedRect(2, 2, 495, 315, 15, 15)
        
        painter.setFont(QFont('Arial', 28, QFont.Weight.Bold))
        painter.setPen(QColor(0, 255, 255))
        painter.drawText(0, 60, 500, 50, Qt.AlignmentFlag.AlignCenter, "🛡️ SECURITY SYSTEM")
        
        painter.setFont(QFont('Arial', 12))
        painter.setPen(QColor(150, 150, 255))
        painter.drawText(0, 100, 500, 30, Qt.AlignmentFlag.AlignCenter, "Advanced AI-Powered Monitoring")
        
        painter.end()
        
        super().__init__(pixmap)
        self.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        
        self.progress = 0
        self.status_text = "Initializing..."
    
    def drawContents(self, painter):
        painter.setFont(QFont('Arial', 11))
        painter.setPen(QColor(0, 255, 255))
        painter.drawText(0, 200, 500, 30, Qt.AlignmentFlag.AlignCenter, self.status_text)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 30, 60))
        painter.drawRoundedRect(50, 240, 400, 20, 10, 10)
        
        if self.progress > 0:
            gradient = QLinearGradient(50, 0, 450, 0)
            gradient.setColorAt(0, QColor(0, 200, 255))
            gradient.setColorAt(1, QColor(0, 255, 200))
            painter.setBrush(gradient)
            width = int(400 * self.progress / 100)
            painter.drawRoundedRect(50, 240, width, 20, 10, 10)
        
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(0, 270, 500, 30, Qt.AlignmentFlag.AlignCenter, f"{self.progress}%")
    
    def setProgress(self, value: int, text: str = ""):
        self.progress = value
        if text:
            self.status_text = text
        self.repaint()


def main():
    has_gpu = check_dependencies()
    
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName("Security System")
    app.setStyle('Fusion')
    
    splash = AnimatedSplash()
    splash.show()
    app.processEvents()
    
    steps = [
        (10, "Loading configuration..."),
        (30, "Starting camera..."),
        (50, "Loading AI models..."),
        (70, "Setting up detectors..."),
        (90, "Connecting services..."),
        (100, "Ready!"),
    ]
    
    current_step = [0]
    
    def update_progress():
        if current_step[0] < len(steps):
            progress, text = steps[current_step[0]]
            splash.setProgress(progress, text)
            current_step[0] += 1
            app.processEvents()
    
    update_progress()
    QTimer.singleShot(100, update_progress)
    app.processEvents()
    
    from gui import SecuritySystemWindow
    
    update_progress()
    app.processEvents()
    
    window = SecuritySystemWindow(has_gpu=has_gpu)
    
    for i in range(current_step[0], len(steps)):
        update_progress()
        app.processEvents()
        QTimer.singleShot(100 * i, lambda: None)
    
    def show_main():
        splash.close()
        window.show()
    
    QTimer.singleShot(800, show_main)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
