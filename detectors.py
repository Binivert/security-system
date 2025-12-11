#!/usr/bin/env python3
"""Detection modules - Enhanced with partial skeleton detection for reliable zone breach."""

import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
import threading
from queue import Queue, Empty
import warnings
import time
import shutil

warnings.filterwarnings('ignore')

from config import Config, Sensitivity

# Check for YOLO availability
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("WARNING: ultralytics not installed. Run: pip install ultralytics")

# Face recognition
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

# MediaPipe for skeleton detection
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print("WARNING: mediapipe not installed. Run: pip install mediapipe")


@dataclass
class SkeletonLandmark:
    """Individual skeleton landmark."""
    x: int
    y: int
    visibility: float
    name: str


@dataclass
class PartialBodyDetection:
    """Detected body part."""
    part_type: str  # 'face', 'hand_left', 'hand_right', 'foot_left', 'foot_right', 'torso', 'arm', 'leg'
    center: Tuple[int, int]
    bbox: Optional[Tuple[int, int, int, int]] = None  # left, top, right, bottom
    confidence: float = 0.0


@dataclass
class PersonDetection:
    """Detected person data with skeleton information."""
    center: Tuple[int, int]
    foot_center: Tuple[int, int]
    bbox: Tuple[int, int, int, int]  # left, top, right, bottom
    confidence: float
    skeleton_landmarks: List[SkeletonLandmark] = field(default_factory=list)
    partial_detections: List[PartialBodyDetection] = field(default_factory=list)
    has_full_skeleton: bool = False


@dataclass
class FaceDetection:
    """Detected face data."""
    name: str
    confidence: float
    is_trusted: bool
    bbox: Tuple[int, int, int, int]


class PersonDetector:
    """Enhanced person detector with partial skeleton detection."""
    
    # MediaPipe Pose landmark indices
    POSE_LANDMARKS = {
        'nose': 0,
        'left_eye_inner': 1, 'left_eye': 2, 'left_eye_outer': 3,
        'right_eye_inner': 4, 'right_eye': 5, 'right_eye_outer': 6,
        'left_ear': 7, 'right_ear': 8,
        'mouth_left': 9, 'mouth_right': 10,
        'left_shoulder': 11, 'right_shoulder': 12,
        'left_elbow': 13, 'right_elbow': 14,
        'left_wrist': 15, 'right_wrist': 16,
        'left_pinky': 17, 'right_pinky': 18,
        'left_index': 19, 'right_index': 20,
        'left_thumb': 21, 'right_thumb': 22,
        'left_hip': 23, 'right_hip': 24,
        'left_knee': 25, 'right_knee': 26,
        'left_ankle': 27, 'right_ankle': 28,
        'left_heel': 29, 'right_heel': 30,
        'left_foot_index': 31, 'right_foot_index': 32
    }
    
    # Body part groupings for partial detection
    FACE_LANDMARKS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    LEFT_HAND_LANDMARKS = [15, 17, 19, 21]
    RIGHT_HAND_LANDMARKS = [16, 18, 20, 22]
    LEFT_FOOT_LANDMARKS = [27, 29, 31]
    RIGHT_FOOT_LANDMARKS = [28, 30, 32]
    TORSO_LANDMARKS = [11, 12, 23, 24]
    LEFT_ARM_LANDMARKS = [11, 13, 15]
    RIGHT_ARM_LANDMARKS = [12, 14, 16]
    LEFT_LEG_LANDMARKS = [23, 25, 27]
    RIGHT_LEG_LANDMARKS = [24, 26, 28]
    
    def __init__(self, config: Config):
        self.config = config
        self.model = None
        self.confidence_threshold = config.YOLO_CONFIDENCE
        self.skeleton_confidence = config.SKELETON_CONFIDENCE
        self._lock = threading.Lock()
        
        # Initialize YOLO
        if YOLO_AVAILABLE:
            try:
                self.model = YOLO('yolov8n.pt')
                print("YOLOv8 model loaded successfully")
            except Exception as e:
                print(f"Failed to load YOLO model: {e}")
                self.model = None
        
        # Initialize MediaPipe Pose for skeleton detection
        self.pose = None
        self.mp_pose = None
        self.mp_draw = None
        if MEDIAPIPE_AVAILABLE:
            self.mp_pose = mp.solutions.pose
            self.mp_draw = mp.solutions.drawing_utils
            self.mp_drawing_styles = mp.solutions.drawing_styles
            self.pose = self.mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,  # Use medium complexity for better detection
                smooth_landmarks=True,
                enable_segmentation=False,
                min_detection_confidence=0.3,
                min_tracking_confidence=0.3
            )
    
    def set_sensitivity(self, sensitivity: Sensitivity):
        """Update detection sensitivity."""
        settings = self.config.get_sensitivity_settings(sensitivity)
        self.confidence_threshold = settings.get('yolo_confidence', 0.4)
        self.skeleton_confidence = settings.get('skeleton_confidence', 0.5)
        
        # Update MediaPipe confidence if available
        if MEDIAPIPE_AVAILABLE and self.pose:
            self.pose = self.mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                smooth_landmarks=True,
                enable_segmentation=False,
                min_detection_confidence=self.skeleton_confidence,
                min_tracking_confidence=self.skeleton_confidence
            )
        
        print(f"Detection sensitivity: yolo={self.confidence_threshold}, skeleton={self.skeleton_confidence}")
    
    def detect(self, frame: np.ndarray) -> Tuple[List[PersonDetection], np.ndarray]:
        """Detect people using YOLO + MediaPipe skeleton detection."""
        if frame is None or frame.size == 0:
            return [], frame
        
        h, w = frame.shape[:2]
        persons = []
        
        # First, run skeleton detection on full frame for partial body detection
        skeleton_detections = self._detect_skeletons(frame)
        
        # Then run YOLO for person bounding boxes
        yolo_persons = self._detect_yolo(frame)
        
        # Merge YOLO detections with skeleton data
        persons = self._merge_detections(yolo_persons, skeleton_detections, w, h)
        
        # If no YOLO detection but skeleton found, create person from skeleton
        if not yolo_persons and skeleton_detections:
            for skel in skeleton_detections:
                person = self._create_person_from_skeleton(skel, w, h)
                if person:
                    persons.append(person)
        
        # Draw detections on frame
        frame = self._draw_detections(frame, persons)
        
        return persons, frame
    
    def _detect_yolo(self, frame: np.ndarray) -> List[Dict]:
        """Run YOLO person detection."""
        if self.model is None:
            return []
        
        yolo_persons = []
        try:
            with self._lock:
                results = self.model(
                    frame,
                    conf=self.confidence_threshold,
                    classes=[0],  # Person class
                    verbose=False
                )
            
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    
                    if cls == 0:  # Person
                        yolo_persons.append({
                            'bbox': (int(x1), int(y1), int(x2), int(y2)),
                            'confidence': conf
                        })
        except Exception as e:
            pass
        
        return yolo_persons
    
    def _detect_skeletons(self, frame: np.ndarray) -> List[Dict]:
        """Detect skeletons using MediaPipe Pose."""
        if self.pose is None:
            return []
        
        skeletons = []
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb)
            
            if results.pose_landmarks:
                h, w = frame.shape[:2]
                landmarks = []
                
                for idx, lm in enumerate(results.pose_landmarks.landmark):
                    px = int(lm.x * w)
                    py = int(lm.y * h)
                    visibility = lm.visibility
                    
                    # Get landmark name
                    name = list(self.POSE_LANDMARKS.keys())[idx] if idx < len(self.POSE_LANDMARKS) else f"point_{idx}"
                    
                    landmarks.append({
                        'idx': idx,
                        'x': px,
                        'y': py,
                        'visibility': visibility,
                        'name': name
                    })
                
                skeletons.append({
                    'landmarks': landmarks,
                    'raw_results': results
                })
        except Exception as e:
            pass
        
        return skeletons
    
    def _merge_detections(self, yolo_persons: List[Dict], skeletons: List[Dict], w: int, h: int) -> List[PersonDetection]:
        """Merge YOLO and skeleton detections."""
        persons = []
        
        for yolo in yolo_persons:
            x1, y1, x2, y2 = yolo['bbox']
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            foot_y = y2
            
            person = PersonDetection(
                center=(cx, cy),
                foot_center=(cx, foot_y),
                bbox=yolo['bbox'],
                confidence=yolo['confidence'],
                skeleton_landmarks=[],
                partial_detections=[],
                has_full_skeleton=False
            )
            
            # Try to match with skeleton
            best_skeleton = None
            best_overlap = 0
            
            for skel in skeletons:
                overlap = self._calculate_skeleton_overlap(yolo['bbox'], skel['landmarks'])
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_skeleton = skel
            
            if best_skeleton and best_overlap > 0.3:
                person = self._enrich_with_skeleton(person, best_skeleton, w, h)
            
            persons.append(person)
        
        return persons
    
    def _calculate_skeleton_overlap(self, bbox: Tuple, landmarks: List[Dict]) -> float:
        """Calculate how much of skeleton is inside bbox."""
        x1, y1, x2, y2 = bbox
        inside = 0
        visible = 0
        
        for lm in landmarks:
            if lm['visibility'] > 0.3:
                visible += 1
                if x1 <= lm['x'] <= x2 and y1 <= lm['y'] <= y2:
                    inside += 1
        
        return inside / visible if visible > 0 else 0
    
    def _enrich_with_skeleton(self, person: PersonDetection, skeleton: Dict, w: int, h: int) -> PersonDetection:
        """Add skeleton data to person detection."""
        landmarks = skeleton['landmarks']
        
        # Convert to SkeletonLandmark objects
        for lm in landmarks:
            person.skeleton_landmarks.append(SkeletonLandmark(
                x=lm['x'],
                y=lm['y'],
                visibility=lm['visibility'],
                name=lm['name']
            ))
        
        # Detect partial body parts
        person.partial_detections = self._detect_partial_bodies(landmarks, w, h)
        
        # Check if full skeleton is visible
        visible_count = sum(1 for lm in landmarks if lm['visibility'] > self.skeleton_confidence)
        person.has_full_skeleton = visible_count >= 20
        
        # Update foot center with actual foot position if available
        foot_landmarks = [lm for lm in landmarks if lm['idx'] in self.LEFT_FOOT_LANDMARKS + self.RIGHT_FOOT_LANDMARKS]
        visible_feet = [lm for lm in foot_landmarks if lm['visibility'] > 0.3]
        if visible_feet:
            foot_x = sum(lm['x'] for lm in visible_feet) // len(visible_feet)
            foot_y = max(lm['y'] for lm in visible_feet)
            person.foot_center = (foot_x, foot_y)
        
        return person
    
    def _detect_partial_bodies(self, landmarks: List[Dict], w: int, h: int) -> List[PartialBodyDetection]:
        """Detect visible partial body parts."""
        partials = []
        
        # Check face
        face_lms = [lm for lm in landmarks if lm['idx'] in self.FACE_LANDMARKS and lm['visibility'] > 0.3]
        if len(face_lms) >= 3:
            xs = [lm['x'] for lm in face_lms]
            ys = [lm['y'] for lm in face_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='face',
                center=(cx, cy),
                bbox=(min(xs) - 20, min(ys) - 20, max(xs) + 20, max(ys) + 20),
                confidence=sum(lm['visibility'] for lm in face_lms) / len(face_lms)
            ))
        
        # Check left hand
        left_hand_lms = [lm for lm in landmarks if lm['idx'] in self.LEFT_HAND_LANDMARKS and lm['visibility'] > 0.3]
        if len(left_hand_lms) >= 2:
            xs = [lm['x'] for lm in left_hand_lms]
            ys = [lm['y'] for lm in left_hand_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='hand_left',
                center=(cx, cy),
                bbox=(min(xs) - 15, min(ys) - 15, max(xs) + 15, max(ys) + 15),
                confidence=sum(lm['visibility'] for lm in left_hand_lms) / len(left_hand_lms)
            ))
        
        # Check right hand
        right_hand_lms = [lm for lm in landmarks if lm['idx'] in self.RIGHT_HAND_LANDMARKS and lm['visibility'] > 0.3]
        if len(right_hand_lms) >= 2:
            xs = [lm['x'] for lm in right_hand_lms]
            ys = [lm['y'] for lm in right_hand_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='hand_right',
                center=(cx, cy),
                bbox=(min(xs) - 15, min(ys) - 15, max(xs) + 15, max(ys) + 15),
                confidence=sum(lm['visibility'] for lm in right_hand_lms) / len(right_hand_lms)
            ))
        
        # Check left foot
        left_foot_lms = [lm for lm in landmarks if lm['idx'] in self.LEFT_FOOT_LANDMARKS and lm['visibility'] > 0.3]
        if len(left_foot_lms) >= 2:
            xs = [lm['x'] for lm in left_foot_lms]
            ys = [lm['y'] for lm in left_foot_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='foot_left',
                center=(cx, cy),
                bbox=(min(xs) - 10, min(ys) - 10, max(xs) + 10, max(ys) + 10),
                confidence=sum(lm['visibility'] for lm in left_foot_lms) / len(left_foot_lms)
            ))
        
        # Check right foot
        right_foot_lms = [lm for lm in landmarks if lm['idx'] in self.RIGHT_FOOT_LANDMARKS and lm['visibility'] > 0.3]
        if len(right_foot_lms) >= 2:
            xs = [lm['x'] for lm in right_foot_lms]
            ys = [lm['y'] for lm in right_foot_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='foot_right',
                center=(cx, cy),
                bbox=(min(xs) - 10, min(ys) - 10, max(xs) + 10, max(ys) + 10),
                confidence=sum(lm['visibility'] for lm in right_foot_lms) / len(right_foot_lms)
            ))
        
        # Check torso
        torso_lms = [lm for lm in landmarks if lm['idx'] in self.TORSO_LANDMARKS and lm['visibility'] > 0.3]
        if len(torso_lms) >= 3:
            xs = [lm['x'] for lm in torso_lms]
            ys = [lm['y'] for lm in torso_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='torso',
                center=(cx, cy),
                bbox=(min(xs) - 20, min(ys) - 20, max(xs) + 20, max(ys) + 20),
                confidence=sum(lm['visibility'] for lm in torso_lms) / len(torso_lms)
            ))
        
        # Check arms
        left_arm_lms = [lm for lm in landmarks if lm['idx'] in self.LEFT_ARM_LANDMARKS and lm['visibility'] > 0.3]
        if len(left_arm_lms) >= 2:
            xs = [lm['x'] for lm in left_arm_lms]
            ys = [lm['y'] for lm in left_arm_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='arm_left',
                center=(cx, cy),
                confidence=sum(lm['visibility'] for lm in left_arm_lms) / len(left_arm_lms)
            ))
        
        right_arm_lms = [lm for lm in landmarks if lm['idx'] in self.RIGHT_ARM_LANDMARKS and lm['visibility'] > 0.3]
        if len(right_arm_lms) >= 2:
            xs = [lm['x'] for lm in right_arm_lms]
            ys = [lm['y'] for lm in right_arm_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='arm_right',
                center=(cx, cy),
                confidence=sum(lm['visibility'] for lm in right_arm_lms) / len(right_arm_lms)
            ))
        
        # Check legs
        left_leg_lms = [lm for lm in landmarks if lm['idx'] in self.LEFT_LEG_LANDMARKS and lm['visibility'] > 0.3]
        if len(left_leg_lms) >= 2:
            xs = [lm['x'] for lm in left_leg_lms]
            ys = [lm['y'] for lm in left_leg_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='leg_left',
                center=(cx, cy),
                confidence=sum(lm['visibility'] for lm in left_leg_lms) / len(left_leg_lms)
            ))
        
        right_leg_lms = [lm for lm in landmarks if lm['idx'] in self.RIGHT_LEG_LANDMARKS and lm['visibility'] > 0.3]
        if len(right_leg_lms) >= 2:
            xs = [lm['x'] for lm in right_leg_lms]
            ys = [lm['y'] for lm in right_leg_lms]
            cx, cy = sum(xs) // len(xs), sum(ys) // len(ys)
            partials.append(PartialBodyDetection(
                part_type='leg_right',
                center=(cx, cy),
                confidence=sum(lm['visibility'] for lm in right_leg_lms) / len(right_leg_lms)
            ))
        
        return partials
    
    def _create_person_from_skeleton(self, skeleton: Dict, w: int, h: int) -> Optional[PersonDetection]:
        """Create a PersonDetection from skeleton data when no YOLO detection."""
        landmarks = skeleton['landmarks']
        visible_lms = [lm for lm in landmarks if lm['visibility'] > 0.3]
        
        if len(visible_lms) < 5:
            return None
        
        xs = [lm['x'] for lm in visible_lms]
        ys = [lm['y'] for lm in visible_lms]
        
        x1, y1 = max(0, min(xs) - 20), max(0, min(ys) - 20)
        x2, y2 = min(w, max(xs) + 20), min(h, max(ys) + 20)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        
        person = PersonDetection(
            center=(cx, cy),
            foot_center=(cx, y2),
            bbox=(x1, y1, x2, y2),
            confidence=sum(lm['visibility'] for lm in visible_lms) / len(visible_lms),
            skeleton_landmarks=[],
            partial_detections=[],
            has_full_skeleton=False
        )
        
        return self._enrich_with_skeleton(person, skeleton, w, h)
    
    def _draw_detections(self, frame: np.ndarray, persons: List[PersonDetection]) -> np.ndarray:
        """Draw all detections on frame."""
        for person in persons:
            x1, y1, x2, y2 = person.bbox
            
            # Draw bounding box
            color = (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label = f"Person {person.confidence:.0%}"
            if person.has_full_skeleton:
                label += " [Full]"
            elif person.partial_detections:
                parts = [p.part_type for p in person.partial_detections]
                label += f" [{len(parts)} parts]"
            
            cv2.putText(frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            # Draw skeleton
            if person.skeleton_landmarks and self.mp_pose and self.mp_draw:
                self._draw_skeleton(frame, person)
            
            # Draw partial body markers
            for partial in person.partial_detections:
                px, py = partial.center
                part_color = self._get_part_color(partial.part_type)
                cv2.circle(frame, (px, py), 8, part_color, -1)
                cv2.putText(frame, partial.part_type[:4], (px - 15, py - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, part_color, 1)
            
            # Draw foot center marker
            cv2.circle(frame, person.foot_center, 5, (255, 0, 255), -1)
        
        return frame
    
    def _draw_skeleton(self, frame: np.ndarray, person: PersonDetection):
        """Draw skeleton connections."""
        if not person.skeleton_landmarks:
            return
        
        # Define connections
        connections = [
            (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),  # Arms
            (11, 23), (12, 24), (23, 24),  # Torso
            (23, 25), (25, 27), (24, 26), (26, 28),  # Legs
            (27, 29), (29, 31), (28, 30), (30, 32),  # Feet
            (0, 1), (1, 2), (2, 3), (3, 7),  # Face left
            (0, 4), (4, 5), (5, 6), (6, 8),  # Face right
        ]
        
        lm_dict = {lm.name: lm for lm in person.skeleton_landmarks}
        idx_to_name = {v: k for k, v in self.POSE_LANDMARKS.items()}
        
        for start_idx, end_idx in connections:
            start_name = idx_to_name.get(start_idx)
            end_name = idx_to_name.get(end_idx)
            
            if start_name in lm_dict and end_name in lm_dict:
                start_lm = lm_dict[start_name]
                end_lm = lm_dict[end_name]
                
                if start_lm.visibility > 0.3 and end_lm.visibility > 0.3:
                    cv2.line(frame, (start_lm.x, start_lm.y), (end_lm.x, end_lm.y),
                            (0, 255, 255), 2)
        
        # Draw landmarks
        for lm in person.skeleton_landmarks:
            if lm.visibility > 0.3:
                cv2.circle(frame, (lm.x, lm.y), 4, (255, 0, 255), -1)
    
    def _get_part_color(self, part_type: str) -> Tuple[int, int, int]:
        """Get color for body part."""
        colors = {
            'face': (0, 255, 255),
            'hand_left': (255, 165, 0),
            'hand_right': (255, 165, 0),
            'foot_left': (255, 0, 0),
            'foot_right': (255, 0, 0),
            'torso': (0, 255, 0),
            'arm_left': (255, 200, 0),
            'arm_right': (255, 200, 0),
            'leg_left': (0, 200, 255),
            'leg_right': (0, 200, 255),
        }
        return colors.get(part_type, (255, 255, 255))


class FaceRecognitionEngine:
    """Face recognition with auto-processing of trusted faces."""
    
    def __init__(self, config: Config):
        self.config = config
        self.known_faces = {}
        self.known_names = []
        self._lock = threading.Lock()
        self._processed_files = set()
        self._last_check = 0
        self._load_faces()
    
    def _load_faces(self):
        """Load trusted faces from fixed_images directory."""
        if not FACE_RECOGNITION_AVAILABLE:
            return
        
        with self._lock:
            self.known_faces.clear()
            self.known_names.clear()
            
            # Process any new images in trusted_faces folder
            self._process_new_trusted_faces()
            
            # Load from fixed_images (processed database)
            if not self.config.FIXED_IMAGES_DIR.exists():
                return
            
            for fp in self.config.FIXED_IMAGES_DIR.iterdir():
                if fp.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp'}:
                    try:
                        img = cv2.imread(str(fp))
                        if img is None:
                            continue
                        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        locs = face_recognition.face_locations(rgb, model="hog")
                        if locs:
                            enc = face_recognition.face_encodings(rgb, locs)
                            if enc:
                                self.known_faces[fp.stem] = enc[0]
                                self.known_names.append(fp.stem)
                                print(f"Loaded trusted face: {fp.stem}")
                    except Exception as e:
                        print(f"Error loading face {fp}: {e}")
    
    def _process_new_trusted_faces(self):
        """Process new images from trusted_faces folder and move to fixed_images."""
        if not FACE_RECOGNITION_AVAILABLE:
            return
        
        if not self.config.TRUSTED_FACES_DIR.exists():
            return
        
        for fp in self.config.TRUSTED_FACES_DIR.iterdir():
            if fp.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp'}:
                if str(fp) in self._processed_files:
                    continue
                
                try:
                    # Load and verify face exists
                    img = cv2.imread(str(fp))
                    if img is None:
                        continue
                    
                    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    locs = face_recognition.face_locations(rgb, model="hog")
                    
                    if locs:
                        # Face found, copy to fixed_images
                        dest = self.config.FIXED_IMAGES_DIR / fp.name
                        shutil.copy2(str(fp), str(dest))
                        print(f"Processed and added trusted face: {fp.stem}")
                        self._processed_files.add(str(fp))
                    else:
                        print(f"No face found in {fp.name}, skipping")
                except Exception as e:
                    print(f"Error processing {fp}: {e}")
    
    def check_for_new_faces(self):
        """Check for new trusted face images (call periodically)."""
        now = time.time()
        if now - self._last_check < self.config.TRUSTED_FACES_CHECK_INTERVAL:
            return
        
        self._last_check = now
        
        # Check for new files
        if self.config.TRUSTED_FACES_DIR.exists():
            current_files = set(str(f) for f in self.config.TRUSTED_FACES_DIR.iterdir()
                               if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp'})
            new_files = current_files - self._processed_files
            
            if new_files:
                self._load_faces()
    
    def reload_faces(self):
        """Reload trusted faces."""
        self._processed_files.clear()
        self._load_faces()
    
    def recognize_faces(self, frame: np.ndarray) -> List[FaceDetection]:
        """Recognize faces in frame."""
        if not FACE_RECOGNITION_AVAILABLE or frame is None:
            return []
        
        # Check for new trusted faces
        self.check_for_new_faces()
        
        results = []
        try:
            h, w = frame.shape[:2]
            scale = self.config.FACE_DETECTION_SCALE
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            
            locs = face_recognition.face_locations(rgb, model="hog")
            if not locs:
                return []
            
            encs = face_recognition.face_encodings(rgb, locs)
            
            with self._lock:
                for (top, right, bottom, left), enc in zip(locs, encs):
                    # Scale back to original size
                    top = int(top / scale)
                    right = int(right / scale)
                    bottom = int(bottom / scale)
                    left = int(left / scale)
                    
                    name = "Unknown"
                    conf = 0.0
                    trusted = False
                    
                    if self.known_names:
                        known_encs = list(self.known_faces.values())
                        matches = face_recognition.compare_faces(
                            known_encs, enc, self.config.FACE_MATCH_TOLERANCE
                        )
                        dists = face_recognition.face_distance(known_encs, enc)
                        
                        if len(dists) > 0:
                            best = np.argmin(dists)
                            if matches[best]:
                                name = self.known_names[best]
                                conf = 1.0 - dists[best]
                                trusted = True
                    
                    results.append(FaceDetection(
                        name=name,
                        confidence=conf,
                        is_trusted=trusted,
                        bbox=(left, top, right, bottom)
                    ))
        except Exception:
            pass
        
        return results


class MotionDetector:
    """Motion detection with heat map generation."""
    
    def __init__(self, config: Config):
        self.config = config
        self.prev_frame = None
        self.heat_map = None
        self.frame_size = None
        self.threshold = config.MOTION_THRESHOLD
        self.min_area = config.MOTION_MIN_AREA
    
    def set_sensitivity(self, sensitivity: Sensitivity):
        """Update motion detection sensitivity."""
        settings = self.config.get_sensitivity_settings(sensitivity)
        self.threshold = settings.get('motion_threshold', 25)
        self.min_area = settings.get('motion_min_area', 500)
    
    def detect(self, frame: np.ndarray) -> Tuple[bool, np.ndarray, List[Tuple]]:
        """Detect motion in frame."""
        if frame is None:
            return False, np.zeros((480, 640), dtype=np.uint8), []
        
        h, w = frame.shape[:2]
        size = (w, h)
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        
        if self.frame_size != size or self.prev_frame is None:
            self.prev_frame = gray
            self.heat_map = np.zeros_like(gray, dtype=np.float32)
            self.frame_size = size
            return False, np.zeros_like(gray), []
        
        # Frame difference
        delta = cv2.absdiff(self.prev_frame, gray)
        thresh = cv2.threshold(delta, self.threshold, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        
        # Update heat map with decay
        self.heat_map = self.heat_map * 0.92 + thresh.astype(np.float32) * 0.08
        self.prev_frame = gray
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        regions = []
        has_motion = False
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > self.min_area:
                has_motion = True
                x, y, cw, ch = cv2.boundingRect(cnt)
                regions.append((x, y, x + cw, y + ch))
        
        return has_motion, thresh, regions
    
    def get_heat_map(self) -> Optional[np.ndarray]:
        """Get motion heat map."""
        if self.heat_map is None:
            return None
        return np.clip(self.heat_map, 0, 255).astype(np.uint8)


class DetectionThread(threading.Thread):
    """Background thread for detection processing."""
    
    def __init__(self, person_detector: PersonDetector, motion_detector: MotionDetector):
        super().__init__(daemon=True)
        self.person_detector = person_detector
        self.motion_detector = motion_detector
        self._input_queue = Queue(maxsize=2)
        self._running = False
        
        self.last_persons: List[PersonDetection] = []
        self.last_motion = False
        self.last_motion_regions: List[Tuple] = []
        self.last_frame: Optional[np.ndarray] = None
        self._result_lock = threading.Lock()
    
    def run(self):
        """Main detection loop."""
        self._running = True
        while self._running:
            try:
                frame = self._input_queue.get(timeout=0.1)
                
                # Run person detection (includes skeleton)
                persons, processed = self.person_detector.detect(frame)
                
                # Run motion detection
                motion, _, regions = self.motion_detector.detect(frame)
                
                with self._result_lock:
                    self.last_persons = persons
                    self.last_motion = motion
                    self.last_motion_regions = regions
                    self.last_frame = processed
                    
            except Empty:
                continue
            except Exception:
                pass
    
    def stop(self):
        """Stop the detection thread."""
        self._running = False
    
    def submit(self, frame: np.ndarray):
        """Submit a frame for processing."""
        try:
            self._input_queue.put_nowait(frame.copy())
        except Exception:
            pass
    
    def get_results(self) -> dict:
        """Get latest detection results."""
        with self._result_lock:
            return {
                'persons': self.last_persons.copy() if self.last_persons else [],
                'motion': self.last_motion,
                'motion_regions': self.last_motion_regions.copy() if self.last_motion_regions else [],
                'frame': self.last_frame.copy() if self.last_frame is not None else None
            }
