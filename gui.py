#!/usr/bin/env python3
"""Main GUI - Enhanced with comprehensive zone breach detection."""

import cv2
import numpy as np
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
import threading

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QFrame, QGroupBox, QScrollArea, QMessageBox,
    QCheckBox, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QMouseEvent, QKeyEvent

from config import Config, AlertType, Sensitivity
from database import DatabaseManager
from detectors import (
    PersonDetector, FaceRecognitionEngine, MotionDetector, 
    DetectionThread, FACE_RECOGNITION_AVAILABLE, YOLO_AVAILABLE,
    PersonDetection, PartialBodyDetection
)
from telegram_bot import TelegramBot
from audio import TTSEngine, ContinuousAlarm
from utils import DetectionZone3D, MultiZoneManager, CornerDetector


class CameraThread(QThread):
    """Camera capture thread."""
    frame_ready = pyqtSignal(np.ndarray)
    fps_updated = pyqtSignal(float)
    error = pyqtSignal(str)
    
    def __init__(self, camera_id=0, width=1280, height=720):
        super().__init__()
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.running = False
        self.cap = None
        self.brightness = 0
        self.contrast = 1.0
    
    def run(self):
        for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]:
            try:
                self.cap = cv2.VideoCapture(self.camera_id, backend)
                if self.cap.isOpened():
                    ret, _ = self.cap.read()
                    if ret:
                        break
                    self.cap.release()
            except Exception:
                pass
        
        if not self.cap or not self.cap.isOpened():
            self.error.emit(f"Cannot open camera {self.camera_id}")
            return
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.running = True
        count = 0
        start = time.time()
        
        while self.running:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                if self.brightness != 0 or self.contrast != 1.0:
                    frame = cv2.convertScaleAbs(frame, alpha=self.contrast, beta=self.brightness)
                self.frame_ready.emit(frame)
                count += 1
                if time.time() - start >= 1.0:
                    self.fps_updated.emit(count / (time.time() - start))
                    count = 0
                    start = time.time()
            else:
                time.sleep(0.01)
        
        if self.cap:
            self.cap.release()
    
    def stop(self):
        self.running = False
        self.wait(2000)


class VideoThread(QThread):
    """Video file playback thread."""
    frame_ready = pyqtSignal(np.ndarray)
    position_updated = pyqtSignal(int, int, float)
    ended = pyqtSignal()
    
    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.running = False
        self.paused = False
        self.cap = None
        self.seek_to = -1
        self.fps = 30
        self.total_frames = 0
        self._lock = threading.Lock()
        self.loop = True
    
    def run(self):
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            return
        
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        delay = 1.0 / self.fps
        
        self.running = True
        
        while self.running:
            with self._lock:
                if self.seek_to >= 0:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.seek_to)
                    self.seek_to = -1
            
            if not self.paused:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                    self.frame_ready.emit(frame)
                    self.position_updated.emit(pos, self.total_frames, self.fps)
                    time.sleep(delay)
                else:
                    if self.loop:
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    else:
                        self.ended.emit()
                        self.paused = True
            else:
                time.sleep(0.05)
        
        if self.cap:
            self.cap.release()
    
    def stop(self):
        self.running = False
        self.wait(2000)
    
    def seek(self, frame: int):
        with self._lock:
            self.seek_to = max(0, min(frame, self.total_frames - 1))
    
    def skip(self, seconds: float):
        if self.cap:
            with self._lock:
                pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
                self.seek_to = max(0, min(int(pos + seconds * self.fps), self.total_frames - 1))


class ClickableSlider(QSlider):
    """Slider that responds to clicks."""
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
        super().mousePressEvent(event)


class VideoWidget(QLabel):
    """Video display widget with zone drawing support."""
    zone_clicked = pyqtSignal(int, int)
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background-color: #0a0a1a; border-radius: 8px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drawing = False
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.frame_w = 1280
        self.frame_h = 720
    
    def mousePressEvent(self, e: QMouseEvent):
        if self.drawing and e.button() == Qt.MouseButton.LeftButton:
            pos = e.position()
            x = int((pos.x() - self.offset_x) / self.scale_x)
            y = int((pos.y() - self.offset_y) / self.scale_y)
            x = max(0, min(x, self.frame_w - 1))
            y = max(0, min(y, self.frame_h - 1))
            self.zone_clicked.emit(x, y)
    
    def update_frame(self, frame: np.ndarray):
        if frame is None or frame.size == 0:
            return
        
        h, w = frame.shape[:2]
        self.frame_w, self.frame_h = w, h
        
        ww, wh = self.width(), self.height()
        if ww <= 0 or wh <= 0:
            return
        
        scale = min(ww / w, wh / h)
        nw, nh = int(w * scale), int(h * scale)
        
        self.scale_x = self.scale_y = scale
        self.offset_x = (ww - nw) // 2
        self.offset_y = (wh - nh) // 2
        
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb = np.ascontiguousarray(rgb)
            qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qimg).scaled(
                nw, nh, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(pix)
        except Exception:
            pass


class SecuritySystemWindow(QMainWindow):
    """Main application window with enhanced detection."""
    
    def __init__(self):
        super().__init__()
        
        # Initialize components
        self.config = Config()
        self.db = DatabaseManager(self.config)
        self.person_detector = PersonDetector(self.config)
        self.face_engine = FaceRecognitionEngine(self.config)
        self.motion_detector = MotionDetector(self.config)
        self.telegram = TelegramBot(self.config)
        self.tts = TTSEngine()
        self.alarm = ContinuousAlarm(self.config)
        self.zone_manager = MultiZoneManager()
        self.corner_detector = CornerDetector()
        
        # Detection thread
        self.detection_thread = DetectionThread(self.person_detector, self.motion_detector)
        
        # State
        self.is_armed = False
        self.is_recording = False
        self.video_writer = None
        self.current_frame = None
        self.processed_frame = None
        self.cameras = []
        self.alert_count = 0
        self.current_fps = 0
        self.start_time = time.time()
        
        self.breach_active = False
        self.breach_start = 0
        self.last_breach_photo = 0
        self.trusted_detected = False
        self.trusted_name = ""
        self.trusted_timeout = 0
        self.breached_ids: List[int] = []
        self.greeted_persons = set()  # Track who we've greeted
        
        self.night_vision = False
        self.show_heat_map = True  # Enable heat map by default
        self.auto_record = False
        self.person_count = 0
        self.sensitivity = Sensitivity.MEDIUM
        
        self.source = 'camera'
        self.video_thread = None
        self.camera_thread = None
        self.video_path = None
        
        # Setup
        self._detect_cameras()
        self._setup_ui()
        self._apply_theme()
        self._connect()
        
        # Start threads
        self.detection_thread.start()
        self._start_camera()
        
        self.telegram.start()
        self.tts.start()
        
        # Startup message
        QTimer.singleShot(2000, self._startup_msg)
        
        # Display timer (60 FPS)
        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self._update_display)
        self.display_timer.start(16)
        
        # Processing timer (20 FPS)
        self.process_timer = QTimer()
        self.process_timer.timeout.connect(self._process)
        self.process_timer.start(50)
    
    def _detect_cameras(self):
        """Detect available cameras."""
        self.cameras = []
        for i in range(5):
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        self.cameras.append(i)
                    cap.release()
            except Exception:
                pass
        if not self.cameras:
            self.cameras = [0]
    
    def _setup_ui(self):
        """Setup the user interface."""
        self.setWindowTitle("🛡️ Security System - Enhanced Detection")
        self.setMinimumSize(1400, 900)
        
        central = QWidget()
        self.setCentralWidget(central)
        main = QHBoxLayout(central)
        main.setSpacing(10)
        main.setContentsMargins(10, 10, 10, 10)
        
        # Video section
        video_frame = QFrame()
        video_frame.setObjectName("videoFrame")
        vl = QVBoxLayout(video_frame)
        vl.setContentsMargins(8, 8, 8, 8)
        
        self.video_widget = VideoWidget()
        vl.addWidget(self.video_widget, 1)
        
        # Source toggle row
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Source:"))
        
        self.source_toggle = QPushButton("📹 Live Camera")
        self.source_toggle.setObjectName("toggleButton")
        self.source_toggle.setCheckable(True)
        self.source_toggle.setMinimumWidth(140)
        self.source_toggle.clicked.connect(self._toggle_source)
        src_row.addWidget(self.source_toggle)
        
        self.camera_label = QLabel("Camera:")
        src_row.addWidget(self.camera_label)
        
        self.camera_combo = QComboBox()
        for c in self.cameras:
            self.camera_combo.addItem(f"Camera {c}", c)
        self.camera_combo.currentIndexChanged.connect(self._change_camera)
        src_row.addWidget(self.camera_combo)
        
        self.load_video_btn = QPushButton("📁 Load Video")
        self.load_video_btn.clicked.connect(self._load_video)
        self.load_video_btn.setVisible(False)
        src_row.addWidget(self.load_video_btn)
        
        src_row.addStretch()
        vl.addLayout(src_row)
        
        # Video controls
        self.video_controls = QWidget()
        vc_layout = QHBoxLayout(self.video_controls)
        vc_layout.setContentsMargins(0, 5, 0, 0)
        
        self.skip_back_btn = QPushButton("⏪")
        self.skip_back_btn.setToolTip("Back 10s")
        self.skip_back_btn.setFixedSize(45, 35)
        self.skip_back_btn.clicked.connect(lambda: self._skip(-10))
        vc_layout.addWidget(self.skip_back_btn)
        
        self.play_btn = QPushButton("⏸")
        self.play_btn.setFixedSize(45, 35)
        self.play_btn.clicked.connect(self._toggle_pause)
        vc_layout.addWidget(self.play_btn)
        
        self.skip_fwd_btn = QPushButton("⏩")
        self.skip_fwd_btn.setToolTip("Forward 10s")
        self.skip_fwd_btn.setFixedSize(45, 35)
        self.skip_fwd_btn.clicked.connect(lambda: self._skip(10))
        vc_layout.addWidget(self.skip_fwd_btn)
        
        self.video_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.video_slider.sliderMoved.connect(self._on_slider_moved)
        vc_layout.addWidget(self.video_slider, 1)
        
        self.pos_label = QLabel("00:00 / 00:00")
        vc_layout.addWidget(self.pos_label)
        
        self.video_controls.setVisible(False)
        vl.addWidget(self.video_controls)
        
        # Info bar
        info_bar = QHBoxLayout()
        self.time_label = QLabel("--:--:--")
        self.time_label.setObjectName("infoLabel")
        info_bar.addWidget(self.time_label)
        info_bar.addStretch()
        
        # Detection status
        self.detection_status = QLabel("YOLO: " + ("✓" if YOLO_AVAILABLE else "✗"))
        self.detection_status.setObjectName("infoLabel")
        self.detection_status.setStyleSheet(
            "color: #0f0;" if YOLO_AVAILABLE else "color: #f00;"
        )
        info_bar.addWidget(self.detection_status)
        
        self.fps_label = QLabel("FPS: --")
        self.fps_label.setObjectName("infoLabel")
        info_bar.addWidget(self.fps_label)
        
        self.person_label = QLabel("👤 0")
        self.person_label.setObjectName("personLabel")
        info_bar.addWidget(self.person_label)
        
        self.src_label = QLabel("📹")
        self.src_label.setObjectName("infoLabel")
        info_bar.addWidget(self.src_label)
        vl.addLayout(info_bar)
        
        main.addWidget(video_frame, 7)
        
        # Control panel
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("controlScroll")
        scroll.setFixedWidth(380)
        
        panel = QWidget()
        panel.setObjectName("controlPanel")
        pl = QVBoxLayout(panel)
        pl.setSpacing(8)
        pl.setContentsMargins(10, 10, 10, 10)
        
        title = QLabel("🛡️ SECURITY")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(title)
        
        # Status
        status_frame = QFrame()
        status_frame.setObjectName("statusFrame")
        sl = QHBoxLayout(status_frame)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #f44; font-size: 24px;")
        sl.addWidget(self.status_dot)
        self.status_text = QLabel("DISARMED")
        self.status_text.setStyleSheet("font-size: 16px; font-weight: bold;")
        sl.addWidget(self.status_text)
        sl.addStretch()
        pl.addWidget(status_frame)
        
        # Controls
        ctrl_grp = QGroupBox("⚡ Controls")
        cl = QVBoxLayout(ctrl_grp)
        
        self.arm_btn = QPushButton("🔒 ARM SYSTEM")
        self.arm_btn.setObjectName("armButton")
        self.arm_btn.setCheckable(True)
        self.arm_btn.setMinimumHeight(50)
        self.arm_btn.clicked.connect(self._toggle_arm)
        cl.addWidget(self.arm_btn)
        
        btn_row = QHBoxLayout()
        self.record_btn = QPushButton("⏺ Record")
        self.record_btn.setObjectName("recordButton")
        self.record_btn.setCheckable(True)
        self.record_btn.clicked.connect(self._toggle_record)
        btn_row.addWidget(self.record_btn)
        
        self.snap_btn = QPushButton("📸 Snap")
        self.snap_btn.clicked.connect(self._snapshot)
        btn_row.addWidget(self.snap_btn)
        cl.addLayout(btn_row)
        
        self.mute_btn = QPushButton("🔇 Mute")
        self.mute_btn.setCheckable(True)
        self.mute_btn.clicked.connect(self._toggle_mute)
        cl.addWidget(self.mute_btn)
        
        pl.addWidget(ctrl_grp)
        
        # Camera settings
        cam_grp = QGroupBox("📹 Camera Settings")
        caml = QVBoxLayout(cam_grp)
        
        bl = QHBoxLayout()
        bl.addWidget(QLabel("Brightness:"))
        self.bright_slider = QSlider(Qt.Orientation.Horizontal)
        self.bright_slider.setRange(-100, 100)
        self.bright_slider.setValue(0)
        self.bright_slider.valueChanged.connect(self._brightness_changed)
        bl.addWidget(self.bright_slider)
        caml.addLayout(bl)
        
        contl = QHBoxLayout()
        contl.addWidget(QLabel("Contrast:"))
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(50, 200)
        self.contrast_slider.setValue(100)
        self.contrast_slider.valueChanged.connect(self._contrast_changed)
        contl.addWidget(self.contrast_slider)
        caml.addLayout(contl)
        
        pl.addWidget(cam_grp)
        
        # Detection settings
        det_grp = QGroupBox("🎯 Detection")
        detl = QVBoxLayout(det_grp)
        
        sensl = QHBoxLayout()
        sensl.addWidget(QLabel("Sensitivity:"))
        self.sens_combo = QComboBox()
        self.sens_combo.addItems(["Low", "Medium", "High"])
        self.sens_combo.setCurrentIndex(1)
        self.sens_combo.currentTextChanged.connect(self._sens_changed)
        sensl.addWidget(self.sens_combo)
        detl.addLayout(sensl)
        
        self.sens_info = QLabel("Confidence: 40%")
        self.sens_info.setStyleSheet("color: #888; font-size: 10px;")
        detl.addWidget(self.sens_info)
        
        pl.addWidget(det_grp)
        
        # Zones
        zone_grp = QGroupBox("🎯 Zones")
        zl = QVBoxLayout(zone_grp)
        
        zb = QHBoxLayout()
        self.new_zone_btn = QPushButton("➕ New")
        self.new_zone_btn.clicked.connect(self._new_zone)
        zb.addWidget(self.new_zone_btn)
        
        self.draw_btn = QPushButton("✏️ Draw")
        self.draw_btn.setCheckable(True)
        self.draw_btn.clicked.connect(self._toggle_draw)
        zb.addWidget(self.draw_btn)
        zl.addLayout(zb)
        
        zb2 = QHBoxLayout()
        self.optimize_btn = QPushButton("🔧 Optimize")
        self.optimize_btn.clicked.connect(self._optimize_zone)
        zb2.addWidget(self.optimize_btn)
        
        self.clear_btn = QPushButton("🗑️ Clear")
        self.clear_btn.clicked.connect(self._clear_zones)
        zb2.addWidget(self.clear_btn)
        zl.addLayout(zb2)
        
        self.auto_btn = QPushButton("🤖 Auto-Detect")
        self.auto_btn.clicked.connect(self._auto_zone)
        zl.addWidget(self.auto_btn)
        
        self.zone_info = QLabel("Zones: 0 | Points: 0")
        zl.addWidget(self.zone_info)
        
        pl.addWidget(zone_grp)
        
        # Features
        feat_grp = QGroupBox("✨ Features")
        fl = QVBoxLayout(feat_grp)
        
        self.night_cb = QCheckBox("🌙 Night Vision")
        self.night_cb.toggled.connect(lambda x: setattr(self, 'night_vision', x))
        fl.addWidget(self.night_cb)
        
        self.heat_cb = QCheckBox("🔥 Motion Heat Map")
        self.heat_cb.setChecked(True)
        self.heat_cb.toggled.connect(lambda x: setattr(self, 'show_heat_map', x))
        fl.addWidget(self.heat_cb)
        
        self.auto_rec_cb = QCheckBox("📹 Auto-Record")
        self.auto_rec_cb.toggled.connect(lambda x: setattr(self, 'auto_record', x))
        fl.addWidget(self.auto_rec_cb)
        
        pl.addWidget(feat_grp)
        
        # Stats
        stats_grp = QGroupBox("📊 Stats")
        statsl = QVBoxLayout(stats_grp)
        self.alerts_label = QLabel("Alerts: 0")
        statsl.addWidget(self.alerts_label)
        self.breach_label = QLabel("Zone: Clear")
        self.breach_label.setStyleSheet("color: #0f0;")
        statsl.addWidget(self.breach_label)
        self.breach_time_label = QLabel("Duration: --")
        statsl.addWidget(self.breach_time_label)
        self.detection_info = QLabel("Detection: --")
        self.detection_info.setStyleSheet("color: #888; font-size: 10px;")
        statsl.addWidget(self.detection_info)
        pl.addWidget(stats_grp)
        
        # Faces
        face_grp = QGroupBox("👤 Trusted Faces")
        facel = QVBoxLayout(face_grp)
        self.faces_label = QLabel(f"Loaded: {len(self.face_engine.known_names)}")
        facel.addWidget(self.faces_label)
        self.faces_info = QLabel("Drop images in trusted_faces/")
        self.faces_info.setStyleSheet("color: #888; font-size: 10px;")
        facel.addWidget(self.faces_info)
        self.reload_btn = QPushButton("🔄 Reload Faces")
        self.reload_btn.clicked.connect(self._reload_faces)
        facel.addWidget(self.reload_btn)
        pl.addWidget(face_grp)
        
        pl.addStretch()
        
        scroll.setWidget(panel)
        main.addWidget(scroll)
        
        self.statusBar().showMessage("Ready - Enhanced detection with skeleton and motion")
    
    def _apply_theme(self):
        """Apply dark theme."""
        self.setStyleSheet("""
            QMainWindow { background-color: #050510; }
            QFrame#videoFrame {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0a0a20,stop:1 #050515);
                border: 2px solid #1a1a4a;
                border-radius: 12px;
            }
            QScrollArea#controlScroll { background: transparent; border: none; }
            QWidget#controlPanel {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0a0a20,stop:1 #050515);
                border: 2px solid #1a1a4a;
                border-radius: 12px;
            }
            QFrame#statusFrame {
                background-color: #0a0a25;
                border: 1px solid #2a2a5a;
                border-radius: 8px;
                padding: 8px;
            }
            QLabel { color: #c0c0ff; font-size: 12px; }
            QLabel#titleLabel { color: #0ff; font-size: 18px; font-weight: bold; padding: 10px; }
            QLabel#infoLabel {
                color: #0ff; font-size: 11px;
                background-color: #0a0a25;
                padding: 4px 8px;
                border-radius: 4px;
                border: 1px solid #2a2a5a;
            }
            QLabel#personLabel {
                color: #0ff; font-size: 14px; font-weight: bold;
                background-color: #0a0a25;
                padding: 4px 10px;
                border-radius: 4px;
                border: 1px solid #0aa;
            }
            QGroupBox {
                color: #0ff; font-size: 12px; font-weight: bold;
                border: 1px solid #2a2a6a;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2a2a6a,stop:1 #1a1a4a);
                color: #e0e0ff;
                border: 1px solid #4a4a9a;
                border-radius: 6px;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #3a3a8a,stop:1 #2a2a6a);
                border-color: #0ff;
            }
            QPushButton#armButton {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1a5a1a,stop:1 #0a3a0a);
                border-color: #2a8a2a;
                font-size: 14px;
            }
            QPushButton#armButton:checked {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #6a1a1a,stop:1 #4a0a0a);
                border-color: #f44;
            }
            QPushButton#recordButton:checked {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #8a1a1a,stop:1 #5a0a0a);
                border-color: #f44;
            }
            QPushButton#toggleButton {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1a4a6a,stop:1 #0a2a4a);
            }
            QPushButton#toggleButton:checked {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #6a1a6a,stop:1 #4a0a4a);
                border-color: #f0f;
            }
            QComboBox {
                background-color: #1a1a4a;
                color: #e0e0ff;
                border: 1px solid #4a4a8a;
                border-radius: 4px;
                padding: 8px;
            }
            QSlider::groove:horizontal { background: #1a1a4a; height: 8px; border-radius: 4px; }
            QSlider::handle:horizontal {
                background: #0ff;
                width: 18px; height: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::sub-page:horizontal { background: #0aa; border-radius: 4px; }
            QCheckBox { color: #c0c0ff; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 2px solid #4a4a8a; background: #1a1a3a; }
            QCheckBox::indicator:checked { background: #0aa; border-color: #0ff; }
            QStatusBar { background-color: #0a0a20; color: #0ff; }
            QScrollBar:vertical { background: #0a0a20; width: 10px; }
            QScrollBar::handle:vertical { background: #3a3a7a; border-radius: 5px; min-height: 20px; }
        """)
    
    def _connect(self):
        """Connect signals."""
        self.video_widget.zone_clicked.connect(self._add_zone_point)
        self.telegram.message_received.connect(self._telegram_cmd)
    
    def _start_camera(self):
        """Start camera capture."""
        cam = self.cameras[0] if self.cameras else 0
        self.camera_thread = CameraThread(cam, self.config.FRAME_WIDTH, self.config.FRAME_HEIGHT)
        self.camera_thread.frame_ready.connect(self._on_frame)
        self.camera_thread.fps_updated.connect(self._on_fps)
        self.camera_thread.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self.camera_thread.start()
    
    def _toggle_source(self, checked):
        """Toggle between camera and video source."""
        if checked:
            self.source_toggle.setText("📁 Video File")
            self.src_label.setText("📁")
            self.camera_label.setVisible(False)
            self.camera_combo.setVisible(False)
            self.load_video_btn.setVisible(True)
            self.video_controls.setVisible(True)
            self.source = 'video'
            
            if self.camera_thread:
                self.camera_thread.stop()
                self.camera_thread = None
        else:
            self.source_toggle.setText("📹 Live Camera")
            self.src_label.setText("📹")
            self.camera_label.setVisible(True)
            self.camera_combo.setVisible(True)
            self.load_video_btn.setVisible(False)
            self.video_controls.setVisible(False)
            self.source = 'camera'
            
            if self.video_thread:
                self.video_thread.stop()
                self.video_thread = None
            
            self._start_camera()
    
    def _load_video(self):
        """Load a video file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "", "Video (*.mp4 *.avi *.mkv *.mov)"
        )
        if path:
            if self.video_thread:
                self.video_thread.stop()
            
            self.video_path = path
            self.video_thread = VideoThread(path)
            self.video_thread.frame_ready.connect(self._on_frame)
            self.video_thread.position_updated.connect(self._on_pos)
            self.video_thread.ended.connect(self._on_ended)
            self.video_thread.start()
            self.play_btn.setText("⏸")
    
    def _change_camera(self, idx):
        """Change camera source."""
        if self.source == 'camera' and self.camera_thread:
            cam = self.camera_combo.currentData()
            if cam is not None:
                self.camera_thread.stop()
                self.camera_thread = CameraThread(
                    cam, self.config.FRAME_WIDTH, self.config.FRAME_HEIGHT
                )
                self.camera_thread.frame_ready.connect(self._on_frame)
                self.camera_thread.fps_updated.connect(self._on_fps)
                self.camera_thread.brightness = self.bright_slider.value()
                self.camera_thread.contrast = self.contrast_slider.value() / 100.0
                self.camera_thread.start()
    
    def _toggle_pause(self):
        """Toggle video pause."""
        if self.video_thread:
            self.video_thread.paused = not self.video_thread.paused
            self.play_btn.setText("▶" if self.video_thread.paused else "⏸")
    
    def _skip(self, sec):
        """Skip video by seconds."""
        if self.video_thread:
            self.video_thread.skip(sec)
    
    def _on_slider_moved(self, value):
        """Handle slider movement."""
        if self.video_thread:
            self.video_thread.seek(value)
    
    def _on_pos(self, pos, total, fps):
        """Update video position display."""
        self.video_slider.setMaximum(total)
        self.video_slider.setValue(pos)
        
        cur_s = int(pos / fps) if fps > 0 else 0
        tot_s = int(total / fps) if fps > 0 else 0
        self.pos_label.setText(f"{cur_s//60:02d}:{cur_s%60:02d} / {tot_s//60:02d}:{tot_s%60:02d}")
    
    def _on_ended(self):
        """Handle video end."""
        self.play_btn.setText("▶")
    
    def _on_frame(self, frame):
        """Handle new frame."""
        if frame is not None:
            self.current_frame = frame.copy()
            self.detection_thread.submit(frame)
    
    def _on_fps(self, fps):
        """Update FPS display."""
        self.current_fps = fps
        self.fps_label.setText(f"FPS: {fps:.0f}")
    
    def _brightness_changed(self, val):
        """Handle brightness change."""
        if self.camera_thread:
            self.camera_thread.brightness = val
    
    def _contrast_changed(self, val):
        """Handle contrast change."""
        if self.camera_thread:
            self.camera_thread.contrast = val / 100.0
    
    def _update_display(self):
        """Update video display."""
        if self.processed_frame is not None:
            self.video_widget.update_frame(self.processed_frame)
        elif self.current_frame is not None:
            self.video_widget.update_frame(self.current_frame)
    
    def _check_zone_breach(self, person: PersonDetection, motion_regions: List[Tuple], has_motion: bool) -> bool:
        """Check if person or any body part breaches zone.
        
        Returns True if:
        - Person bounding box overlaps zone
        - Any skeleton landmark is inside zone
        - Any partial body detection overlaps zone
        - Motion detected AND partial skeleton overlaps zone
        """
        if self.zone_manager.get_zone_count() == 0:
            return False
        
        # Check person bounding box
        x1, y1, x2, y2 = person.bbox
        corners = [(x1, y1), (x2, y1), (x1, y2), (x2, y2), person.center, person.foot_center]
        
        for px, py in corners:
            if self.zone_manager.check_all_zones(px, py):
                return True
        
        # Check skeleton landmarks
        for lm in person.skeleton_landmarks:
            if lm.visibility > 0.3:
                if self.zone_manager.check_all_zones(lm.x, lm.y):
                    return True
        
        # Check partial body detections
        for partial in person.partial_detections:
            px, py = partial.center
            if self.zone_manager.check_all_zones(px, py):
                return True
            
            # Check partial bbox if available
            if partial.bbox:
                bx1, by1, bx2, by2 = partial.bbox
                for bx, by in [(bx1, by1), (bx2, by1), (bx1, by2), (bx2, by2)]:
                    if self.zone_manager.check_all_zones(bx, by):
                        return True
        
        # Motion + partial skeleton check
        if has_motion and (person.skeleton_landmarks or person.partial_detections):
            # Check if any motion region overlaps with person area
            for mx1, my1, mx2, my2 in motion_regions:
                # Motion region overlaps person bbox
                if not (mx2 < x1 or mx1 > x2 or my2 < y1 or my1 > y2):
                    # Motion near person, check if in zone
                    motion_center = ((mx1 + mx2) // 2, (my1 + my2) // 2)
                    if self.zone_manager.check_all_zones(*motion_center):
                        return True
        
        return False
    
    def _process(self):
        """Process detection results."""
        if self.current_frame is None:
            return
        
        results = self.detection_thread.get_results()
        det_frame = results.get('frame')
        persons = results.get('persons', [])
        has_motion = results.get('motion', False)
        motion_regions = results.get('motion_regions', [])
        
        frame = det_frame if det_frame is not None else self.current_frame.copy()
        h, w = frame.shape[:2]
        
        # Night vision effect
        if self.night_vision:
            frame = cv2.convertScaleAbs(frame, alpha=1.5, beta=30)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            frame[:, :, 1] = np.clip(frame[:, :, 1] * 1.3, 0, 255).astype(np.uint8)
        
        # Timestamp
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(ts)
        cv2.putText(frame, ts, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        # Heat map overlay for motion visualization
        if self.show_heat_map:
            hm = self.motion_detector.get_heat_map()
            if hm is not None:
                if hm.shape[:2] != frame.shape[:2]:
                    hm = cv2.resize(hm, (w, h))
                hm_color = cv2.applyColorMap(hm, cv2.COLORMAP_JET)
                frame = cv2.addWeighted(frame, 0.7, hm_color, 0.3, 0)
        
        # Draw motion regions
        for mx1, my1, mx2, my2 in motion_regions:
            cv2.rectangle(frame, (mx1, my1), (mx2, my2), (0, 165, 255), 1)
        
        # Update person count
        self.person_count = len(persons)
        self.person_label.setText(f"👤 {self.person_count}")
        
        # Update detection info
        skeleton_count = sum(1 for p in persons if p.skeleton_landmarks)
        partial_count = sum(len(p.partial_detections) for p in persons)
        self.detection_info.setText(f"Skeletons: {skeleton_count} | Parts: {partial_count} | Motion: {'Yes' if has_motion else 'No'}")
        
        now = time.time()
        
        # Trusted person timeout
        if self.trusted_detected and now > self.trusted_timeout:
            self.trusted_detected = False
            self.trusted_name = ""
        
        # Zone breach detection
        self.breached_ids.clear()
        triggered = False
        intruder_detected = False
        
        if self.is_armed and self.zone_manager.get_zone_count() > 0:
            for person in persons:
                # Check comprehensive zone breach
                if self._check_zone_breach(person, motion_regions, has_motion):
                    triggered = True
                    intruder_detected = True
                    
                    # Mark breached zones
                    for zone in self.zone_manager.zones:
                        if zone.zone_id not in self.breached_ids:
                            self.breached_ids.append(zone.zone_id)
                    
                    # Draw intruder marker
                    left, top, right, bottom = person.bbox
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 3)
                    cv2.putText(frame, "⚠ INTRUDER", (left, top - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            
            # Also check if motion alone triggers (when combined with any person detection)
            if has_motion and persons:
                for mx1, my1, mx2, my2 in motion_regions:
                    mcx, mcy = (mx1 + mx2) // 2, (my1 + my2) // 2
                    if self.zone_manager.check_all_zones(mcx, mcy):
                        triggered = True
        
        # Face recognition
        if self.is_armed and FACE_RECOGNITION_AVAILABLE and self.person_count > 0:
            faces = self.face_engine.recognize_faces(self.current_frame)
            for face in faces:
                left, top, right, bottom = face.bbox
                color = (0, 255, 0) if face.is_trusted else (0, 0, 255)
                label = f"{face.name}" if face.is_trusted else "UNKNOWN"
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                cv2.putText(frame, label, (left, top - 7), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                
                if face.is_trusted and face.confidence > 0.5:
                    self.trusted_detected = True
                    self.trusted_name = face.name
                    self.trusted_timeout = now + 10  # 10 second timeout
                    
                    # Greet the person if not already greeted recently
                    if face.name not in self.greeted_persons:
                        self.greeted_persons.add(face.name)
                        self.tts.speak(f"Hello {face.name}")
                        # Clear greeting after 60 seconds
                        QTimer.singleShot(60000, lambda n=face.name: self.greeted_persons.discard(n))
        
        # Handle breach
        if triggered and intruder_detected:
            if self.trusted_detected:
                # Trusted person - stop alarm
                self.breach_label.setText(f"Zone: ✅ {self.trusted_name}")
                self.breach_label.setStyleSheet("color: #0f0;")
                self.breach_time_label.setText("Duration: --")
                if self.breach_active:
                    self.breach_active = False
                    self.alarm.stop()
                    self.telegram.send_message(f"✅ Trusted person detected: {self.trusted_name}")
            else:
                # Intruder - trigger alarm
                if not self.breach_active:
                    self.breach_active = True
                    self.breach_start = now
                    self.last_breach_photo = now
                    self.alarm.start()
                    self._alert(frame, "Intruder detected in zone")
                else:
                    if now - self.last_breach_photo >= self.config.BREACH_PHOTO_INTERVAL:
                        self.last_breach_photo = now
                        dur = int(now - self.breach_start)
                        self._alert(frame, f"Still in zone ({dur}s)")
                
                dur = int(now - self.breach_start)
                self.breach_time_label.setText(f"Duration: {dur}s")
                self.breach_label.setText("Zone: ⚠️ BREACH")
                self.breach_label.setStyleSheet("color: #f00; font-weight: bold;")
        else:
            if self.breach_active:
                self.breach_active = False
                self.alarm.stop()
                dur = int(now - self.breach_start)
                self.telegram.send_message(f"✅ Zone Clear\nDuration: {dur}s")
            
            self.breach_label.setText("Zone: Clear")
            self.breach_label.setStyleSheet("color: #0f0;")
            self.breach_time_label.setText("Duration: --")
        
        # Draw zones
        frame = self.zone_manager.draw_all(frame, self.breached_ids)
        
        # Recording indicator
        if self.is_recording:
            cv2.circle(frame, (w - 25, 25), 10, (0, 0, 255), -1)
            cv2.putText(frame, "REC", (w - 65, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            if self.video_writer:
                try:
                    self.video_writer.write(self.current_frame)
                except Exception:
                    pass
        
        # Armed indicator
        if self.is_armed:
            cv2.putText(frame, "ARMED", (w - 80, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        self.processed_frame = frame
    
    def _alert(self, frame, reason):
        """Trigger an alert."""
        self.alert_count += 1
        self.alerts_label.setText(f"Alerts: {self.alert_count}")
        
        if self.auto_record and not self.is_recording:
            self.record_btn.click()
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(self.config.ALERTS_DIR / f"alert_{ts}.jpg")
        try:
            cv2.imwrite(path, frame)
        except Exception:
            path = None
        
        self.db.log_event(AlertType.ZONE_BREACH.value, reason, path, self.person_count)
        self.db.update_daily_stats(alerts=1, breaches=1)
        
        msg = f"🚨 *ALERT*\n{reason}\nPersons: {self.person_count}"
        self.telegram.send_message(msg, path)
        self.tts.speak(f"Alert. {reason}")
    
    def _new_zone(self):
        """Create a new zone."""
        self.zone_manager.create_zone()
        self.draw_btn.setChecked(True)
        self._toggle_draw(True)
        self._update_zone_info()
    
    def _toggle_draw(self, checked):
        """Toggle zone drawing mode."""
        self.video_widget.drawing = checked
        self.draw_btn.setText("✅ Done" if checked else "✏️ Draw")
    
    def _add_zone_point(self, x, y):
        """Add a point to the current zone."""
        zone = self.zone_manager.get_active_zone()
        if zone:
            zone.add_point(x, y)
            self._update_zone_info()
    
    def _optimize_zone(self):
        """Optimize the current zone."""
        zone = self.zone_manager.get_active_zone()
        if zone and zone.is_complete:
            zone.optimize_zone()
            self.tts.speak("Zone optimized")
    
    def _clear_zones(self):
        """Clear all zones."""
        self.zone_manager.delete_all_zones()
        self.breach_active = False
        self.alarm.stop()
        self._update_zone_info()
    
    def _auto_zone(self):
        """Auto-detect zone corners."""
        if self.current_frame is None:
            return
        corners = self.corner_detector.detect_floor_corners(self.current_frame)
        if corners and len(corners) >= 3:
            zone = self.zone_manager.create_zone("Auto Zone")
            for c in corners:
                zone.add_point(c[0], c[1])
            self._update_zone_info()
            self.tts.speak(f"Detected {len(corners)} corners")
        else:
            QMessageBox.information(self, "Auto-Detect", "Could not detect corners. Draw manually.")
    
    def _update_zone_info(self):
        """Update zone info display."""
        zone = self.zone_manager.get_active_zone()
        pts = len(zone.points) if zone else 0
        self.zone_info.setText(f"Zones: {self.zone_manager.get_zone_count()} | Points: {pts}")
    
    def _sens_changed(self, text):
        """Handle sensitivity change."""
        m = {'Low': Sensitivity.LOW, 'Medium': Sensitivity.MEDIUM, 'High': Sensitivity.HIGH}
        self.sensitivity = m.get(text, Sensitivity.MEDIUM)
        self.person_detector.set_sensitivity(self.sensitivity)
        self.motion_detector.set_sensitivity(self.sensitivity)
        
        settings = self.config.get_sensitivity_settings(self.sensitivity)
        conf = settings.get('yolo_confidence', 0.4)
        self.sens_info.setText(f"Confidence: {conf:.0%}")
    
    def _toggle_arm(self, checked=None):
        """Toggle system armed state."""
        if checked is None:
            checked = not self.is_armed
        
        self.is_armed = checked
        self.arm_btn.setChecked(checked)
        
        if checked:
            self.arm_btn.setText("🔓 DISARM")
            self.status_dot.setStyleSheet("color: #0f0; font-size: 24px;")
            self.status_text.setText("ARMED")
            self.status_text.setStyleSheet("color: #0f0; font-size: 16px; font-weight: bold;")
            self.tts.speak("System armed")
            msg = "🔒 *System Armed*"
        else:
            self.arm_btn.setText("🔒 ARM SYSTEM")
            self.status_dot.setStyleSheet("color: #f44; font-size: 24px;")
            self.status_text.setText("DISARMED")
            self.status_text.setStyleSheet("color: #f44; font-size: 16px; font-weight: bold;")
            self.tts.speak("System disarmed")
            self.alarm.stop()
            self.breach_active = False
            msg = "🔓 *System Disarmed*"
        
        self.telegram.update_state(self.is_armed, self.is_recording, self.alarm.is_muted)
        self.telegram.send_message(msg)
    
    def _toggle_record(self, checked=None):
        """Toggle recording."""
        if checked is None:
            checked = not self.is_recording
        
        self.record_btn.setChecked(checked)
        
        if checked:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(self.config.RECORDINGS_DIR / f"rec_{ts}.avi")
            try:
                fourcc = cv2.VideoWriter_fourcc(*'XVID')
                self.video_writer = cv2.VideoWriter(
                    path, fourcc, 25.0, 
                    (self.config.FRAME_WIDTH, self.config.FRAME_HEIGHT)
                )
                self.is_recording = True
                self.record_btn.setText("⏹ Stop")
                self.tts.speak("Recording")
            except Exception:
                self.record_btn.setChecked(False)
        else:
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            self.is_recording = False
            self.record_btn.setText("⏺ Record")
            self.tts.speak("Stopped")
        
        self.telegram.update_state(self.is_armed, self.is_recording, self.alarm.is_muted)
    
    def _snapshot(self):
        """Take a snapshot."""
        if self.current_frame is None:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(self.config.SNAPSHOTS_DIR / f"snap_{ts}.jpg")
        try:
            cv2.imwrite(path, self.current_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            self.tts.speak("Snapshot")
            self.telegram.send_message("📸 Snapshot", path)
        except Exception:
            pass
    
    def _toggle_mute(self, checked=None):
        """Toggle alarm mute."""
        if checked is None:
            checked = not self.alarm.is_muted
        
        self.mute_btn.setChecked(checked)
        if checked:
            self.alarm.mute()
            self.mute_btn.setText("🔊 Unmute")
        else:
            self.alarm.unmute()
            self.mute_btn.setText("🔇 Mute")
        self.telegram.update_state(self.is_armed, self.is_recording, self.alarm.is_muted)
    
    def _reload_faces(self):
        """Reload trusted faces."""
        self.face_engine.reload_faces()
        self.faces_label.setText(f"Loaded: {len(self.face_engine.known_names)}")
        if self.face_engine.known_names:
            self.faces_info.setText(f"Names: {', '.join(self.face_engine.known_names[:3])}...")
        self.tts.speak(f"{len(self.face_engine.known_names)} faces loaded")
    
    def _telegram_cmd(self, cmd, args):
        """Handle Telegram commands."""
        if cmd == 'arm':
            self._toggle_arm(True)
        elif cmd == 'disarm':
            self._toggle_arm(False)
        elif cmd in ['snap', 'snapshot']:
            self._snapshot()
        elif cmd == 'record':
            self._toggle_record(True)
        elif cmd == 'stoprecord':
            self._toggle_record(False)
        elif cmd == 'mute':
            self._toggle_mute(True)
        elif cmd == 'unmute':
            self._toggle_mute(False)
        elif cmd == 'status':
            self._send_status()
        elif cmd == 'stats':
            self._send_stats()
        elif cmd == 'log':
            self._send_log()
        elif cmd == 'reload_faces':
            self._reload_faces()
        elif cmd == 'nightmode':
            self.night_vision = args.lower() == 'on'
            self.night_cb.setChecked(self.night_vision)
            self.telegram.send_message(f"Night vision: {'ON' if self.night_vision else 'OFF'}")
        elif cmd == 'sensitivity':
            m = {'low': 'Low', 'medium': 'Medium', 'high': 'High'}
            if args.lower() in m:
                self.sens_combo.setCurrentText(m[args.lower()])
                self.telegram.send_message(f"Sensitivity: {m[args.lower()]}")
    
    def _send_status(self):
        """Send status via Telegram."""
        s = "🔒 Armed" if self.is_armed else "🔓 Disarmed"
        r = "⏺ Recording" if self.is_recording else "⏹ Not Recording"
        m = "🔇 Muted" if self.alarm.is_muted else "🔊 Active"
        b = "⚠️ BREACH" if self.breach_active else "✅ Clear"
        t = f"✅ {self.trusted_name}" if self.trusted_detected else "❌ None"
        
        msg = f"""📊 *Status*

Security: {s}
Recording: {r}
Alarm: {m}
Zone: {b}
Trusted: {t}
Persons: {self.person_count}
Zones: {self.zone_manager.get_zone_count()}
Alerts: {self.alert_count}
Detector: {'YOLO+Skeleton' if YOLO_AVAILABLE else 'None'}"""
        self.telegram.send_message(msg)
    
    def _send_stats(self):
        """Send stats via Telegram."""
        st = self.db.get_daily_stats()
        msg = f"📈 *Today's Stats*\n\nAlerts: {st['alerts']}\nBreaches: {st['breaches']}"
        self.telegram.send_message(msg)
    
    def _send_log(self):
        """Send log via Telegram."""
        events = self.db.get_recent_events(5)
        msg = "📋 *Recent Events*\n\n"
        if events:
            for e in events:
                msg += f"• {e['timestamp']}: {e['event_type']}\n"
        else:
            msg += "No events."
        self.telegram.send_message(msg)
    
    def _startup_msg(self):
        """Send startup message."""
        self.telegram.send_main_menu()
    
    def keyPressEvent(self, e: QKeyEvent):
        """Handle key presses."""
        k = e.key()
        if k == Qt.Key.Key_Escape and self.isFullScreen():
            self.showMaximized()
        elif k == Qt.Key.Key_F11:
            self.showFullScreen() if not self.isFullScreen() else self.showMaximized()
        elif k == Qt.Key.Key_Space:
            self._snapshot()
        elif k == Qt.Key.Key_A:
            self.arm_btn.click()
        elif k == Qt.Key.Key_R:
            self.record_btn.click()
    
    def showEvent(self, e):
        """Handle show event."""
        super().showEvent(e)
        QTimer.singleShot(100, self.showMaximized)
    
    def closeEvent(self, e):
        """Handle close event."""
        self.alarm.stop()
        self.detection_thread.stop()
        
        if self.camera_thread:
            self.camera_thread.stop()
        if self.video_thread:
            self.video_thread.stop()
        if self.video_writer:
            self.video_writer.release()
        
        self.telegram.stop()
        self.telegram.wait(2000)
        self.tts.stop()
        self.tts.wait(2000)
        
        try:
            self.telegram.send_message("🔴 *System Offline*", reply_markup=None)
        except Exception:
            pass
        
        e.accept()
