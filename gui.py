#!/usr/bin/env python3
"""Main GUI - Simple alarm tied directly to zone color."""

import cv2
import numpy as np
import time
from datetime import datetime
from typing import List, Optional, Tuple
import threading
from queue import Queue

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QGroupBox, QScrollArea, QMessageBox, QCheckBox, QFileDialog, QSlider
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QMouseEvent, QKeyEvent

from config import Config, AlertType
from database import DatabaseManager
from detectors import (
    PersonDetector, FaceRecognitionEngine, MotionDetector, DetectionThread,
    FACE_RECOGNITION_AVAILABLE, download_manager, PersonDetection
)
from telegram_bot import TelegramBot
from audio import TTSEngine, WavAlarm
from utils import MultiZoneManager


class CameraThread(QThread):
    frame_ready = pyqtSignal(np.ndarray, int)
    fps_updated = pyqtSignal(float)
    error = pyqtSignal(str)
    started_signal = pyqtSignal()

    def __init__(self, camera_id: int, width: int, height: int, source_id: int):
        super().__init__()
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.source_id = source_id
        self.running = False
        self.cap = None
        self.paused = False

    def run(self):
        for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]:
            try:
                self.cap = cv2.VideoCapture(self.camera_id, backend)
                if self.cap.isOpened():
                    ret, _ = self.cap.read()
                    if ret:
                        break
                    self.cap.release()
            except:
                pass

        if not self.cap or not self.cap.isOpened():
            self.error.emit(f"Cannot open camera {self.camera_id}")
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.running = True
        self.started_signal.emit()

        count = 0
        start = time.time()

        while self.running:
            if self.paused:
                QThread.msleep(50)
                continue
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.frame_ready.emit(frame, self.source_id)
                count += 1
                if time.time() - start >= 1.0:
                    self.fps_updated.emit(count / (time.time() - start))
                    count = 0
                    start = time.time()
            else:
                QThread.msleep(10)

        if self.cap:
            self.cap.release()

    def stop(self):
        self.running = False
        self.wait(3000)


class VideoThread(QThread):
    frame_ready = pyqtSignal(np.ndarray, int)
    position_updated = pyqtSignal(int, int, float)
    ended = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, path: str, source_id: int):
        super().__init__()
        self.path = path
        self.source_id = source_id
        self.running = False
        self._paused = False
        self.cap = None
        self.seek_to = -1
        self.fps = 30.0
        self.total_frames = 0
        self._lock = threading.Lock()
        self.loop = True

    @property
    def paused(self):
        return self._paused

    @paused.setter
    def paused(self, value):
        self._paused = value

    def run(self):
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            self.error.emit(f"Cannot open: {self.path}")
            return

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0 or self.fps > 120:
            self.fps = 30.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        delay_ms = max(1, int(1000.0 / self.fps))

        self.running = True

        while self.running:
            with self._lock:
                if self.seek_to >= 0:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.seek_to)
                    self.seek_to = -1

            if not self._paused:
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                    self.frame_ready.emit(frame, self.source_id)
                    self.position_updated.emit(pos, self.total_frames, self.fps)
                    QThread.msleep(delay_ms)
                else:
                    if self.loop:
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    else:
                        self.ended.emit()
                        self._paused = True
            else:
                QThread.msleep(50)

        if self.cap:
            self.cap.release()

    def stop(self):
        self.running = False
        self.wait(3000)

    def seek(self, frame: int):
        with self._lock:
            self.seek_to = max(0, min(frame, self.total_frames - 1))

    def skip(self, seconds: float):
        if self.cap:
            with self._lock:
                pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
                self.seek_to = max(0, min(int(pos + seconds * self.fps), self.total_frames - 1))


class VideoWidget(QLabel):
    zone_clicked = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background-color: #050515; border-radius: 8px;")
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
            pix = QPixmap.fromImage(qimg).scaled(nw, nh, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(pix)
        except:
            pass


class SecuritySystemWindow(QMainWindow):

    def __init__(self, has_gpu: bool = False):
        super().__init__()

        self.has_gpu = has_gpu
        self.config = Config()

        self.db = DatabaseManager(self.config)
        self.telegram = TelegramBot(self.config)
        self.tts = TTSEngine()
        self.alarm = WavAlarm(self.config)  # Simple WAV alarm
        self.zone_manager = MultiZoneManager()

        self.person_detector = None
        self.face_engine = None
        self.motion_detector = None
        self.detection_thread = None
        self._models_loaded = False

        self.is_armed = False
        self.is_recording = False
        self.video_writer = None

        self.current_frame = None
        self.display_frame = None
        self._frame_lock = threading.Lock()
        self._source_id = 0

        self.cameras = []
        self.alert_count = 0
        self.current_fps = 0

        # Simple breach tracking
        self.breach_active = False
        self.breach_start_time = 0
        self.photo_sent_this_breach = False
        self.last_telegram_update = 0

        self.trusted_detected = False
        self.trusted_name = ""
        self.trusted_timeout = 0

        self.breached_ids = []
        self.greeted_persons = set()
        self.face_rec_counter = 0

        self.night_vision = False
        self.show_heat_map = False
        self.show_motion_boxes = True
        self.draw_skeleton = False
        self.enable_face = True
        self.enable_motion_breach = True
        self.person_count = 0
        self.confidence = 0.25

        self.source = 'camera'
        self.camera_thread = None
        self.video_thread = None

        # Message queue for Telegram (non-blocking)
        self._msg_queue = Queue()
        self._msg_worker = threading.Thread(target=self._process_messages, daemon=True)
        self._msg_worker.start()

        self._detect_cameras()
        self._setup_ui()
        self._apply_theme()
        self._connect_signals()

        self._start_camera()

        self.telegram.start()
        self.tts.start()

        QTimer.singleShot(500, self._load_models_background)
        QTimer.singleShot(3000, lambda: self.telegram.send_main_menu())

        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self._update_display)
        self.display_timer.start(16)

        self.process_timer = QTimer()
        self.process_timer.timeout.connect(self._process_frame)
        self.process_timer.start(33)

        self.download_check_timer = QTimer()
        self.download_check_timer.timeout.connect(self._check_download_status)
        self.download_check_timer.start(500)

    def _check_download_status(self):
        is_downloading, model_name, _ = download_manager.get_status()
        if is_downloading:
            self.status_label.setText(f"⏳ Downloading {model_name}...")
            self.status_label.setStyleSheet("color: #ff0; font-weight: bold;")
            self.status_label.setVisible(True)
            if self.camera_thread:
                self.camera_thread.paused = True
        else:
            if self._models_loaded:
                self.status_label.setVisible(False)
            if self.camera_thread:
                self.camera_thread.paused = False

    def _load_models_background(self):
        def load():
            try:
                self.person_detector = PersonDetector(self.config)
                self.face_engine = FaceRecognitionEngine(self.config)
                self.motion_detector = MotionDetector(self.config)
                self.detection_thread = DetectionThread(self.person_detector, self.motion_detector)
                self.detection_thread.draw_skeleton = self.draw_skeleton
                self.detection_thread.start()
                self._models_loaded = True
            except Exception as e:
                print(f"[Models] Error: {e}")
                self._models_loaded = True
        threading.Thread(target=load, daemon=True).start()

    def _process_messages(self):
        """Process Telegram messages in background."""
        while True:
            try:
                task = self._msg_queue.get()
                if task is None:
                    break
                action, data = task

                if action == 'intruder_update':
                    duration = data
                    self.telegram.send_message(f"⚠️ *Intruder still in zone* ({duration}s)")
                elif action == 'zone_clear':
                    duration = data
                    self.telegram.send_message(f"✅ *Zone Clear* ({duration}s)")
                elif action == 'message':
                    self.telegram.send_message(data)
                elif action == 'snapshot':
                    frame = data
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = str(self.config.SNAPSHOTS_DIR / f"snap_{ts}.jpg")
                    try:
                        cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                        self.telegram.send_snapshot(path)
                    except:
                        pass
            except Exception as e:
                print(f"[Msg Worker] Error: {e}")

    def _send_intruder_photo(self, frame: np.ndarray, count: int, reason: str):
        """Send intruder photo in background thread."""
        def send():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(self.config.ALERTS_DIR / f"intruder_{ts}.jpg")
            try:
                cv2.imwrite(path, frame)
                try:
                    self.db.log_event(AlertType.ZONE_BREACH.value, reason, path, count)
                except:
                    pass
                self.telegram.send_alert_with_photo(
                    f"🚨 *INTRUDER DETECTED!*\n\n"
                    f"⚠️ {reason}\n"
                    f"👤 Persons: {count}\n"
                    f"🕐 {datetime.now().strftime('%H:%M:%S')}",
                    path
                )
            except Exception as e:
                print(f"[Alert] Error: {e}")
        threading.Thread(target=send, daemon=True).start()

    def _detect_cameras(self):
        self.cameras = []
        for i in range(3):
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        self.cameras.append(i)
                    cap.release()
            except:
                pass
        if not self.cameras:
            self.cameras = [0]

    def _setup_ui(self):
        self.setWindowTitle("🛡️ Security System")
        self.setMinimumSize(1400, 900)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        video_frame = QFrame()
        video_frame.setObjectName("videoFrame")
        video_layout = QVBoxLayout(video_frame)
        video_layout.setContentsMargins(8, 8, 8, 8)

        self.video_widget = VideoWidget()
        video_layout.addWidget(self.video_widget, 1)

        source_row = QHBoxLayout()
        self.source_btn = QPushButton("📹 Live Camera")
        self.source_btn.setCheckable(True)
        self.source_btn.setMinimumWidth(140)
        self.source_btn.clicked.connect(self._toggle_source)
        source_row.addWidget(self.source_btn)

        self.camera_combo = QComboBox()
        for c in self.cameras:
            self.camera_combo.addItem(f"Camera {c}", c)
        self.camera_combo.currentIndexChanged.connect(self._change_camera)
        source_row.addWidget(self.camera_combo)

        self.load_video_btn = QPushButton("📁 Load Video")
        self.load_video_btn.clicked.connect(self._load_video)
        self.load_video_btn.setVisible(False)
        source_row.addWidget(self.load_video_btn)
        source_row.addStretch()
        video_layout.addLayout(source_row)

        self.playback_widget = QWidget()
        playback_layout = QHBoxLayout(self.playback_widget)
        playback_layout.setContentsMargins(0, 5, 0, 0)

        self.skip_back_btn = QPushButton("⏪ -10s")
        self.skip_back_btn.setFixedWidth(70)
        self.skip_back_btn.clicked.connect(lambda: self._skip_video(-10))
        playback_layout.addWidget(self.skip_back_btn)

        self.play_pause_btn = QPushButton("⏸ Pause")
        self.play_pause_btn.setFixedWidth(80)
        self.play_pause_btn.clicked.connect(self._toggle_video_pause)
        playback_layout.addWidget(self.play_pause_btn)

        self.skip_fwd_btn = QPushButton("+10s ⏩")
        self.skip_fwd_btn.setFixedWidth(70)
        self.skip_fwd_btn.clicked.connect(lambda: self._skip_video(10))
        playback_layout.addWidget(self.skip_fwd_btn)

        self.video_slider = QSlider(Qt.Orientation.Horizontal)
        self.video_slider.sliderMoved.connect(self._on_video_seek)
        playback_layout.addWidget(self.video_slider, 1)

        self.video_pos_label = QLabel("00:00 / 00:00")
        playback_layout.addWidget(self.video_pos_label)

        self.playback_widget.setVisible(False)
        video_layout.addWidget(self.playback_widget)

        info_layout = QHBoxLayout()
        self.time_label = QLabel("--:--:--")
        self.time_label.setObjectName("infoLabel")
        info_layout.addWidget(self.time_label)
        info_layout.addStretch()

        self.status_label = QLabel("⏳ Loading AI...")
        self.status_label.setStyleSheet("color: #ff0; font-weight: bold;")
        info_layout.addWidget(self.status_label)

        gpu_text = "🎮 GPU" if self.has_gpu else "💻 CPU"
        self.gpu_label = QLabel(gpu_text)
        self.gpu_label.setObjectName("infoLabel")
        self.gpu_label.setStyleSheet("color: #0f0;" if self.has_gpu else "color: #f80;")
        info_layout.addWidget(self.gpu_label)

        self.fps_label = QLabel("FPS: --")
        self.fps_label.setObjectName("infoLabel")
        info_layout.addWidget(self.fps_label)

        self.person_label = QLabel("👤 0")
        self.person_label.setObjectName("personLabel")
        info_layout.addWidget(self.person_label)

        video_layout.addLayout(info_layout)
        main_layout.addWidget(video_frame, 7)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("controlScroll")
        scroll.setFixedWidth(380)

        panel = QWidget()
        panel.setObjectName("controlPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("🛡️ SECURITY SYSTEM")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(title)

        status_frame = QFrame()
        status_frame.setObjectName("statusFrame")
        status_layout = QHBoxLayout(status_frame)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #ff4444; font-size: 28px;")
        status_layout.addWidget(self.status_dot)
        self.status_text = QLabel("DISARMED")
        self.status_text.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff4444;")
        status_layout.addWidget(self.status_text)
        status_layout.addStretch()
        panel_layout.addWidget(status_frame)

        ctrl_group = QGroupBox("⚡ CONTROLS")
        ctrl_layout = QVBoxLayout(ctrl_group)

        self.arm_btn = QPushButton("🔒 ARM SYSTEM")
        self.arm_btn.setObjectName("armButton")
        self.arm_btn.setCheckable(True)
        self.arm_btn.setMinimumHeight(55)
        self.arm_btn.clicked.connect(self._toggle_arm)
        ctrl_layout.addWidget(self.arm_btn)

        btn_row = QHBoxLayout()
        self.record_btn = QPushButton("⏺ Record")
        self.record_btn.setObjectName("recordButton")
        self.record_btn.setCheckable(True)
        self.record_btn.clicked.connect(self._toggle_record)
        btn_row.addWidget(self.record_btn)

        self.snap_btn = QPushButton("📸 Snap")
        self.snap_btn.clicked.connect(self._take_snapshot)
        btn_row.addWidget(self.snap_btn)
        ctrl_layout.addLayout(btn_row)

        self.mute_btn = QPushButton("🔇 Mute Alarm")
        self.mute_btn.setCheckable(True)
        self.mute_btn.clicked.connect(self._toggle_mute)
        ctrl_layout.addWidget(self.mute_btn)
        panel_layout.addWidget(ctrl_group)

        det_group = QGroupBox("🎯 DETECTION")
        det_layout = QVBoxLayout(det_group)

        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel("Confidence:"))
        self.conf_combo = QComboBox()
        for level in self.config.CONFIDENCE_LEVELS.keys():
            self.conf_combo.addItem(level)
        self.conf_combo.setCurrentText("25%")
        self.conf_combo.currentTextChanged.connect(self._confidence_changed)
        conf_row.addWidget(self.conf_combo)
        det_layout.addLayout(conf_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        for name in self.config.AVAILABLE_MODELS.keys():
            self.model_combo.addItem(name)
        self.model_combo.setCurrentIndex(0)
        self.model_combo.currentTextChanged.connect(self._change_model)
        model_row.addWidget(self.model_combo)
        det_layout.addLayout(model_row)
        panel_layout.addWidget(det_group)

        zone_group = QGroupBox("🎯 ZONES")
        zone_layout = QVBoxLayout(zone_group)
        zone_btn_row = QHBoxLayout()
        self.new_zone_btn = QPushButton("➕ New")
        self.new_zone_btn.clicked.connect(self._new_zone)
        zone_btn_row.addWidget(self.new_zone_btn)
        self.draw_zone_btn = QPushButton("✏️ Draw")
        self.draw_zone_btn.setCheckable(True)
        self.draw_zone_btn.clicked.connect(self._toggle_draw_mode)
        zone_btn_row.addWidget(self.draw_zone_btn)
        self.clear_zones_btn = QPushButton("🗑️ Clear")
        self.clear_zones_btn.clicked.connect(self._clear_zones)
        zone_btn_row.addWidget(self.clear_zones_btn)
        zone_layout.addLayout(zone_btn_row)
        self.zone_info_label = QLabel("Zones: 0")
        zone_layout.addWidget(self.zone_info_label)
        panel_layout.addWidget(zone_group)

        feat_group = QGroupBox("✨ FEATURES")
        feat_layout = QVBoxLayout(feat_group)

        self.skeleton_cb = QCheckBox("🦴 Skeleton Detection")
        self.skeleton_cb.setChecked(False)
        self.skeleton_cb.toggled.connect(self._toggle_skeleton)
        feat_layout.addWidget(self.skeleton_cb)

        self.face_cb = QCheckBox("👤 Face Recognition")
        self.face_cb.setChecked(True)
        self.face_cb.toggled.connect(lambda x: setattr(self, 'enable_face', x))
        feat_layout.addWidget(self.face_cb)

        self.motion_cb = QCheckBox("📡 Motion Detection")
        self.motion_cb.setChecked(True)
        self.motion_cb.toggled.connect(lambda x: setattr(self, 'show_motion_boxes', x))
        feat_layout.addWidget(self.motion_cb)

        self.motion_breach_cb = QCheckBox("🔔 Motion Triggers Breach")
        self.motion_breach_cb.setChecked(True)
        self.motion_breach_cb.toggled.connect(lambda x: setattr(self, 'enable_motion_breach', x))
        feat_layout.addWidget(self.motion_breach_cb)

        self.heat_cb = QCheckBox("🔥 Heat Map")
        self.heat_cb.setChecked(False)
        self.heat_cb.toggled.connect(lambda x: setattr(self, 'show_heat_map', x))
        feat_layout.addWidget(self.heat_cb)

        self.night_cb = QCheckBox("🌙 Night Vision")
        self.night_cb.toggled.connect(lambda x: setattr(self, 'night_vision', x))
        feat_layout.addWidget(self.night_cb)

        panel_layout.addWidget(feat_group)

        stats_group = QGroupBox("📊 STATUS")
        stats_layout = QVBoxLayout(stats_group)
        self.alerts_label = QLabel("Alerts: 0")
        stats_layout.addWidget(self.alerts_label)
        self.breach_label = QLabel("Zone: ✅ Clear")
        self.breach_label.setStyleSheet("color: #00ff00;")
        stats_layout.addWidget(self.breach_label)
        self.breach_time_label = QLabel("Duration: --")
        stats_layout.addWidget(self.breach_time_label)
        self.alarm_status_label = QLabel("Alarm: Off")
        stats_layout.addWidget(self.alarm_status_label)
        panel_layout.addWidget(stats_group)

        face_group = QGroupBox("👤 TRUSTED FACES")
        face_layout = QVBoxLayout(face_group)
        self.faces_label = QLabel("Loaded: 0")
        face_layout.addWidget(self.faces_label)
        self.reload_faces_btn = QPushButton("🔄 Reload")
        self.reload_faces_btn.clicked.connect(self._reload_faces)
        face_layout.addWidget(self.reload_faces_btn)
        panel_layout.addWidget(face_group)

        panel_layout.addStretch()
        scroll.setWidget(panel)
        main_layout.addWidget(scroll)

        self.statusBar().showMessage("Ready")

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #030308; }
            QFrame#videoFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0a0a1a, stop:0.5 #050510, stop:1 #0a0a1a); border: 2px solid #1a1a5a; border-radius: 12px; }
            QScrollArea#controlScroll { background: transparent; border: none; }
            QWidget#controlPanel { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #0a0a1a, stop:1 #050510); border: 2px solid #2a1a5a; border-radius: 12px; }
            QFrame#statusFrame { background-color: #0a0a20; border: 1px solid #3a2a6a; border-radius: 8px; padding: 10px; }
            QLabel { color: #c0c0ff; font-size: 12px; }
            QLabel#titleLabel { color: #00ffff; font-size: 20px; font-weight: bold; padding: 12px; }
            QLabel#infoLabel { color: #00ffff; font-size: 11px; background-color: #0a0a25; padding: 5px 10px; border-radius: 4px; border: 1px solid #2a2a5a; }
            QLabel#personLabel { color: #00ffff; font-size: 14px; font-weight: bold; background-color: #0a0a25; padding: 5px 12px; border-radius: 4px; border: 1px solid #00aaaa; }
            QGroupBox { color: #00ffff; font-size: 12px; font-weight: bold; border: 1px solid #3a2a6a; border-radius: 8px; margin-top: 12px; padding-top: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2a2a6a, stop:1 #1a1a4a); color: #e0e0ff; border: 1px solid #4a4a9a; border-radius: 6px; padding: 10px 16px; font-size: 12px; font-weight: bold; }
            QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3a3a8a, stop:1 #2a2a6a); border-color: #00ffff; }
            QPushButton:checked { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #5a2a7a, stop:1 #3a1a5a); border-color: #ff00ff; }
            QPushButton#armButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #1a6a2a, stop:1 #0a4a1a); border-color: #2a9a3a; font-size: 16px; }
            QPushButton#armButton:checked { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #7a1a1a, stop:1 #5a0a0a); border-color: #ff4444; }
            QPushButton#recordButton:checked { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #8a1a1a, stop:1 #6a0a0a); border-color: #ff4444; }
            QComboBox { background-color: #1a1a4a; color: #e0e0ff; border: 1px solid #4a4a8a; border-radius: 4px; padding: 8px; min-width: 100px; }
            QCheckBox { color: #c0c0ff; }
            QCheckBox::indicator { width: 20px; height: 20px; border-radius: 4px; border: 2px solid #4a4a8a; background: #1a1a3a; }
            QCheckBox::indicator:checked { background: #00aaaa; border-color: #00ffff; }
            QStatusBar { background-color: #0a0a20; color: #00ffff; }
            QScrollBar:vertical { background: #0a0a20; width: 10px; }
            QScrollBar::handle:vertical { background: #3a3a7a; border-radius: 5px; }
            QSlider::groove:horizontal { background: #1a1a4a; height: 8px; border-radius: 4px; }
            QSlider::handle:horizontal { background: #00ffff; width: 18px; height: 18px; margin: -5px 0; border-radius: 9px; }
        """)

    def _connect_signals(self):
        self.video_widget.zone_clicked.connect(self._add_zone_point)
        self.telegram.message_received.connect(self._handle_telegram_cmd)

    def _toggle_skeleton(self, checked):
        self.draw_skeleton = checked
        if self.detection_thread:
            self.detection_thread.draw_skeleton = checked

    def _start_camera(self):
        self._source_id += 1
        cam_id = self.cameras[0] if self.cameras else 0
        self.camera_thread = CameraThread(cam_id, self.config.FRAME_WIDTH, self.config.FRAME_HEIGHT, self._source_id)
        self.camera_thread.frame_ready.connect(self._on_frame)
        self.camera_thread.fps_updated.connect(self._on_fps)
        self.camera_thread.error.connect(self._on_camera_error)
        self.camera_thread.started_signal.connect(lambda: self.statusBar().showMessage("Camera started"))
        self.camera_thread.start()
        self.source = 'camera'

    def _on_camera_error(self, error):
        self.statusBar().showMessage(f"Camera error: {error}")

    def _toggle_source(self, checked):
        self._source_id += 1
        with self._frame_lock:
            self.current_frame = None
            self.display_frame = None
        if self.motion_detector:
            self.motion_detector.reset()

        if checked:
            self.source = 'video'
            self.source_btn.setText("📁 Video File")
            self.camera_combo.setVisible(False)
            self.load_video_btn.setVisible(True)
            self.playback_widget.setVisible(True)
            if self.camera_thread:
                self.camera_thread.stop()
                self.camera_thread = None
        else:
            self.source = 'camera'
            self.source_btn.setText("📹 Live Camera")
            self.camera_combo.setVisible(True)
            self.load_video_btn.setVisible(False)
            self.playback_widget.setVisible(False)
            if self.video_thread:
                self.video_thread.stop()
                self.video_thread = None
            self._start_camera()

    def _load_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*)")
        if not path:
            return
        self._source_id += 1
        if self.video_thread:
            self.video_thread.stop()
        if self.camera_thread:
            self.camera_thread.stop()
            self.camera_thread = None
        with self._frame_lock:
            self.current_frame = None
            self.display_frame = None
        if self.motion_detector:
            self.motion_detector.reset()

        self.video_thread = VideoThread(path, self._source_id)
        self.video_thread.frame_ready.connect(self._on_frame)
        self.video_thread.position_updated.connect(self._on_video_position)
        self.video_thread.ended.connect(self._on_video_ended)
        self.video_thread.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self.video_thread.start()
        self.play_pause_btn.setText("⏸ Pause")

    def _on_frame(self, frame, source_id: int):
        if source_id != self._source_id:
            return
        if frame is not None:
            with self._frame_lock:
                self.current_frame = frame.copy()
            if self.detection_thread:
                self.detection_thread.submit(frame)

    def _on_fps(self, fps):
        self.current_fps = fps
        self.fps_label.setText(f"FPS: {fps:.0f}")

    def _toggle_video_pause(self):
        if self.video_thread:
            self.video_thread.paused = not self.video_thread.paused
            self.play_pause_btn.setText("▶ Play" if self.video_thread.paused else "⏸ Pause")

    def _skip_video(self, seconds):
        if self.video_thread:
            self.video_thread.skip(seconds)

    def _on_video_seek(self, value):
        if self.video_thread:
            self.video_thread.seek(value)

    def _on_video_position(self, pos, total, fps):
        self.video_slider.setMaximum(total)
        self.video_slider.setValue(pos)
        cur_sec = int(pos / fps) if fps > 0 else 0
        tot_sec = int(total / fps) if fps > 0 else 0
        self.video_pos_label.setText(f"{cur_sec//60:02d}:{cur_sec%60:02d} / {tot_sec//60:02d}:{tot_sec%60:02d}")

    def _on_video_ended(self):
        self.play_pause_btn.setText("▶ Play")

    def _change_camera(self, idx):
        if self.source == 'camera' and self.camera_thread:
            cam_id = self.camera_combo.currentData()
            if cam_id is not None:
                self._source_id += 1
                self.camera_thread.stop()
                self.camera_thread = CameraThread(cam_id, self.config.FRAME_WIDTH, self.config.FRAME_HEIGHT, self._source_id)
                self.camera_thread.frame_ready.connect(self._on_frame)
                self.camera_thread.fps_updated.connect(self._on_fps)
                self.camera_thread.start()

    def _confidence_changed(self, text):
        self.confidence = self.config.CONFIDENCE_LEVELS.get(text, 0.25)
        if self.person_detector:
            self.person_detector.set_confidence(self.confidence)

    def _change_model(self, model_name):
        model_path = self.config.AVAILABLE_MODELS.get(model_name)
        if model_path and self.person_detector:
            self.person_detector.change_model(model_path)

    def _update_display(self):
        if self._models_loaded:
            is_downloading, _, _ = download_manager.get_status()
            if not is_downloading:
                self.status_label.setVisible(False)
            if self.face_engine:
                self.faces_label.setText(f"Loaded: {len(self.face_engine.known_names)}")

        # Update alarm status display
        if self.alarm.is_playing:
            if self.alarm.is_muted:
                self.alarm_status_label.setText("Alarm: 🔇 MUTED")
                self.alarm_status_label.setStyleSheet("color: #ffaa00;")
            else:
                self.alarm_status_label.setText("Alarm: 🔊 PLAYING")
                self.alarm_status_label.setStyleSheet("color: #ff4444;")
        else:
            self.alarm_status_label.setText("Alarm: Off")
            self.alarm_status_label.setStyleSheet("color: #00ff00;")

        with self._frame_lock:
            if self.display_frame is not None:
                frame = self.display_frame.copy()
            elif self.current_frame is not None:
                frame = self.current_frame.copy()
            else:
                frame = None

        if frame is not None:
            self.video_widget.update_frame(frame)

    def _check_zone_breach(self, person: PersonDetection, motion_regions: List[Tuple[int, int, int, int]]) -> Tuple[bool, str]:
        if self.zone_manager.get_zone_count() == 0:
            return False, ""

        x1, y1, x2, y2 = person.bbox
        check_points = [
            (x1, y1), (x2, y1), (x1, y2), (x2, y2),
            person.center, person.foot_center,
            ((x1 + x2) // 2, y1), ((x1 + x2) // 2, y2),
            (x1, (y1 + y2) // 2), (x2, (y1 + y2) // 2),
        ]

        for px, py in check_points:
            if self.zone_manager.check_all_zones(px, py):
                return True, "Person detected in zone"

        for lm in person.skeleton_landmarks:
            if lm.visibility > 0.5:
                if self.zone_manager.check_all_zones(lm.x, lm.y):
                    return True, "Person body part in zone"

        return False, ""

    def _check_motion_breach(self, motion_regions: List[Tuple[int, int, int, int]]) -> Tuple[bool, str]:
        if not self.enable_motion_breach or self.zone_manager.get_zone_count() == 0:
            return False, ""

        for mx1, my1, mx2, my2 in motion_regions:
            cx, cy = (mx1 + mx2) // 2, (my1 + my2) // 2
            if self.zone_manager.check_all_zones(cx, cy):
                return True, "Movement detected in zone"

        return False, ""

    def _process_frame(self):
        with self._frame_lock:
            if self.current_frame is None:
                return
            frame = self.current_frame.copy()

        h, w = frame.shape[:2]
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(ts)
        cv2.putText(frame, ts, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        is_downloading, model_name, _ = download_manager.get_status()
        if is_downloading:
            cv2.putText(frame, f"Downloading {model_name}...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            with self._frame_lock:
                self.display_frame = frame
            return

        if not self._models_loaded or self.detection_thread is None:
            cv2.putText(frame, "Loading AI...", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            with self._frame_lock:
                self.display_frame = frame
            return

        results = self.detection_thread.get_results()
        det_frame = results.get('frame')
        persons = results.get('persons', [])
        has_motion = results.get('motion', False)
        motion_regions = results.get('motion_regions', [])

        if det_frame is not None:
            frame = det_frame.copy()
            h, w = frame.shape[:2]

        if self.night_vision:
            frame = cv2.convertScaleAbs(frame, alpha=1.5, beta=30)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            frame[:, :, 1] = np.clip(frame[:, :, 1] * 1.3, 0, 255).astype(np.uint8)

        cv2.putText(frame, ts, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        if self.show_heat_map and self.motion_detector:
            hm = self.motion_detector.get_heat_map()
            if hm is not None:
                if hm.shape[:2] != (h, w):
                    hm = cv2.resize(hm, (w, h))
                hm_color = cv2.applyColorMap(hm, cv2.COLORMAP_JET)
                frame = cv2.addWeighted(frame, 0.7, hm_color, 0.3, 0)

        if self.show_motion_boxes:
            for mx1, my1, mx2, my2 in motion_regions:
                cv2.rectangle(frame, (mx1, my1), (mx2, my2), (0, 165, 255), 1)

        self.person_count = len(persons)
        self.person_label.setText(f"👤 {self.person_count}")

        now = time.time()

        if self.trusted_detected and now > self.trusted_timeout:
            self.trusted_detected = False
            self.trusted_name = ""

        self.breached_ids.clear()
        
        # ============================================================
        # SIMPLE ALARM LOGIC - TIED DIRECTLY TO ZONE COLOR
        # ============================================================
        # intruder_in_zone = True  -> Zone RED, Alarm ON
        # intruder_in_zone = False -> Zone NORMAL, Alarm OFF
        # ============================================================
        
        intruder_in_zone = False
        breach_reason = ""

        # Check for intruders in zone (only if armed)
        if self.is_armed and self.zone_manager.get_zone_count() > 0:
            for person in persons:
                is_breach, reason = self._check_zone_breach(person, motion_regions)
                if is_breach:
                    intruder_in_zone = True
                    breach_reason = reason
                    for zone in self.zone_manager.zones:
                        if zone.zone_id not in self.breached_ids:
                            self.breached_ids.append(zone.zone_id)
                    x1, y1, x2, y2 = person.bbox
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    cv2.putText(frame, "INTRUDER", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # Also check motion if no person breach
            if not intruder_in_zone and has_motion:
                is_motion_breach, motion_reason = self._check_motion_breach(motion_regions)
                if is_motion_breach:
                    intruder_in_zone = True
                    breach_reason = motion_reason
                    for zone in self.zone_manager.zones:
                        if zone.zone_id not in self.breached_ids:
                            self.breached_ids.append(zone.zone_id)

        # Face recognition
        if self.enable_face and FACE_RECOGNITION_AVAILABLE and self.face_engine and persons:
            self.face_rec_counter += 1
            if self.face_rec_counter % 10 == 0:  # Run every 10 frames to reduce lag further
                with self._frame_lock:
                    face_frame = self.current_frame.copy() if self.current_frame is not None else None
                if face_frame is not None:
                    faces = self.face_engine.recognize_faces(face_frame)
                    for face in faces:
                        left, top, right, bottom = face.bbox
                        color = (0, 255, 0) if face.is_trusted else (0, 0, 255)
                        label = face.name if face.is_trusted else "UNKNOWN"
                        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                        cv2.putText(frame, label, (left, top - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        if face.is_trusted and face.confidence > 0.5:
                            self.trusted_detected = True
                            self.trusted_name = face.name
                            self.trusted_timeout = now + 10
                            if face.name not in self.greeted_persons:
                                self.greeted_persons.add(face.name)
                                self.tts.speak(f"Welcome {face.name}")
                                QTimer.singleShot(60000, lambda n=face.name: self.greeted_persons.discard(n))
            else:
                faces = []

        # ============================================================
        # ALARM CONTROL - SIMPLE AND DIRECT
        # ============================================================
        
        if intruder_in_zone and not self.trusted_detected:
            # === INTRUDER IN ZONE - ALARM ON ===
            self.alarm.start()  # Start playing alarm.wav (no-op if already playing)
            
            if not self.breach_active:
                # First detection
                self.breach_active = True
                self.breach_start_time = now
                self.photo_sent_this_breach = False
                self.last_telegram_update = now
                
                self.alert_count += 1
                self.alerts_label.setText(f"Alerts: {self.alert_count}")
                self.tts.speak("Intruder detected")
                
                # Send photo immediately
                with self._frame_lock:
                    alert_frame = self.current_frame.copy() if self.current_frame is not None else frame.copy()
                self._send_intruder_photo(alert_frame, self.person_count, breach_reason)
                self.photo_sent_this_breach = True
            else:
                # Ongoing breach - send Telegram update every 30 seconds
                if now - self.last_telegram_update >= 30:
                    self.last_telegram_update = now
                    duration = int(now - self.breach_start_time)
                    self._msg_queue.put(('intruder_update', duration))
            
            duration = int(now - self.breach_start_time)
            self.breach_label.setText("Zone: ⚠️ BREACH")
            self.breach_label.setStyleSheet("color: #ff4444; font-weight: bold;")
            self.breach_time_label.setText(f"Duration: {duration}s")
        
        elif self.trusted_detected and intruder_in_zone:
            # === TRUSTED PERSON - NO ALARM ===
            self.alarm.stop()  # Stop immediately
            
            if self.breach_active:
                self._msg_queue.put(('message', f"✅ Trusted person: {self.trusted_name}"))
            
            self.breach_active = False
            self.photo_sent_this_breach = False
            self.breach_label.setText(f"Zone: ✅ {self.trusted_name}")
            self.breach_label.setStyleSheet("color: #00ff00;")
            self.breach_time_label.setText("Duration: --")
        
        else:
            # === NO INTRUDER - ALARM OFF ===
            self.alarm.stop()  # Stop immediately
            
            if self.breach_active:
                duration = int(now - self.breach_start_time)
                self._msg_queue.put(('zone_clear', duration))
            
            self.breach_active = False
            self.photo_sent_this_breach = False
            self.breach_label.setText("Zone: ✅ Clear")
            self.breach_label.setStyleSheet("color: #00ff00;")
            self.breach_time_label.setText("Duration: --")

        # Draw zones
        frame = self.zone_manager.draw_all(frame, self.breached_ids, self.is_armed)

        if self.is_recording:
            cv2.circle(frame, (w - 25, 25), 10, (0, 0, 255), -1)
            cv2.putText(frame, "REC", (w - 65, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            if self.video_writer:
                try:
                    with self._frame_lock:
                        if self.current_frame is not None:
                            self.video_writer.write(self.current_frame)
                except:
                    pass

        if self.is_armed:
            cv2.putText(frame, "ARMED", (w - 85, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        with self._frame_lock:
            self.display_frame = frame

    def _new_zone(self):
        self.zone_manager.create_zone()
        self.draw_zone_btn.setChecked(True)
        self._toggle_draw_mode(True)
        self._update_zone_info()

    def _toggle_draw_mode(self, checked):
        self.video_widget.drawing = checked
        self.draw_zone_btn.setText("✅ Done" if checked else "✏️ Draw")

    def _add_zone_point(self, x, y):
        zone = self.zone_manager.get_active_zone()
        if zone:
            zone.add_point(x, y)
            self._update_zone_info()

    def _clear_zones(self):
        self.zone_manager.delete_all_zones()
        self.breach_active = False
        self.photo_sent_this_breach = False
        self.alarm.stop()
        self._update_zone_info()

    def _update_zone_info(self):
        zone = self.zone_manager.get_active_zone()
        pts = len(zone.points) if zone else 0
        self.zone_info_label.setText(f"Zones: {self.zone_manager.get_zone_count()} | Points: {pts}")

    def _toggle_arm(self, checked=None):
        if checked is None:
            checked = not self.is_armed
        self.is_armed = checked
        self.arm_btn.setChecked(checked)
        
        if checked:
            self.arm_btn.setText("🔓 DISARM")
            self.status_dot.setStyleSheet("color: #00ff00; font-size: 28px;")
            self.status_text.setText("ARMED")
            self.status_text.setStyleSheet("font-size: 18px; font-weight: bold; color: #00ff00;")
            self.tts.speak("System armed")
            msg = "🔒 *System Armed*"
        else:
            self.arm_btn.setText("🔒 ARM SYSTEM")
            self.status_dot.setStyleSheet("color: #ff4444; font-size: 28px;")
            self.status_text.setText("DISARMED")
            self.status_text.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff4444;")
            self.tts.speak("System disarmed")
            # STOP ALARM IMMEDIATELY WHEN DISARMED
            self.alarm.stop()
            self.breach_active = False
            self.photo_sent_this_breach = False
            msg = "🔓 *System Disarmed*"
        
        self.telegram.update_state(self.is_armed, self.is_recording, self.alarm.is_muted)
        self._msg_queue.put(('message', msg))
        QTimer.singleShot(500, lambda: self.telegram.send_main_menu())

    def _toggle_record(self, checked=None):
        if checked is None:
            checked = not self.is_recording
        self.record_btn.setChecked(checked)
        if checked:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(self.config.RECORDINGS_DIR / f"rec_{ts}.avi")
            try:
                fourcc = cv2.VideoWriter_fourcc(*'XVID')
                self.video_writer = cv2.VideoWriter(path, fourcc, 25.0, (self.config.FRAME_WIDTH, self.config.FRAME_HEIGHT))
                self.is_recording = True
                self.record_btn.setText("⏹ Stop")
                self.tts.speak("Recording")
            except:
                self.record_btn.setChecked(False)
        else:
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            self.is_recording = False
            self.record_btn.setText("⏺ Record")
            self.tts.speak("Stopped")
        self.telegram.update_state(self.is_armed, self.is_recording, self.alarm.is_muted)

    def _take_snapshot(self):
        with self._frame_lock:
            if self.current_frame is None:
                self.tts.speak("No frame")
                return
            frame = self.current_frame.copy()
        self._msg_queue.put(('snapshot', frame))
        self.tts.speak("Snapshot")

    def _toggle_mute(self, checked=None):
        if checked is None:
            checked = not self.alarm.is_muted
        self.mute_btn.setChecked(checked)
        if checked:
            self.alarm.mute()
            self.mute_btn.setText("🔊 Unmute")
        else:
            self.alarm.unmute()
            self.mute_btn.setText("🔇 Mute Alarm")
        self.telegram.update_state(self.is_armed, self.is_recording, self.alarm.is_muted)

    def _reload_faces(self):
        if self.face_engine:
            self.face_engine.reload_faces()
            self.faces_label.setText(f"Loaded: {len(self.face_engine.known_names)}")
            self.tts.speak(f"{len(self.face_engine.known_names)} faces")

    def _handle_telegram_cmd(self, cmd, args):
        if cmd == 'arm':
            self._toggle_arm(True)
        elif cmd == 'disarm':
            self._toggle_arm(False)
        elif cmd in ['snap', 'snapshot']:
            self._take_snapshot()
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
        elif cmd == 'reload_faces':
            self._reload_faces()

    def _send_status(self):
        s = "🔒 Armed" if self.is_armed else "🔓 Disarmed"
        b = "⚠️ BREACH" if self.breach_active else "✅ Clear"
        g = "🎮 GPU" if self.has_gpu else "💻 CPU"
        a = "🔊 PLAYING" if self.alarm.is_playing else "Off"
        msg = f"📊 *Status*\n\n*Security:* {s}\n*Zone:* {b}\n*Alarm:* {a}\n*Persons:* {self.person_count}\n*FPS:* {self.current_fps:.0f}\n*Hardware:* {g}\n*Alerts:* {self.alert_count}"
        self._msg_queue.put(('message', msg))

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        if k == Qt.Key.Key_Escape and self.isFullScreen():
            self.showMaximized()
        elif k == Qt.Key.Key_F11:
            self.showFullScreen() if not self.isFullScreen() else self.showMaximized()
        elif k == Qt.Key.Key_Space:
            self._take_snapshot()
        elif k == Qt.Key.Key_A:
            self.arm_btn.click()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(100, self.showMaximized)

    def closeEvent(self, e):
        self._msg_queue.put(None)
        self.alarm.stop()
        if self.detection_thread:
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
        e.accept()
