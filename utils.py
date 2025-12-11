#!/usr/bin/env python3
"""Utility classes."""

import cv2
import numpy as np
import math
from typing import List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class DetectionZone3D:
    points: List[Tuple[int, int]] = field(default_factory=list)
    is_complete: bool = False
    zone_id: int = 0
    name: str = "Zone 1"
    color: Tuple[int, int, int] = (0, 255, 255)
    
    zone_height: int = 50
    grid_spacing: int = 25
    animation_phase: float = 0.0
    scan_offset: float = 0.0
    
    def add_point(self, x: int, y: int):
        self.points.append((x, y))
        if len(self.points) >= 3:
            self.is_complete = True
    
    def reset(self):
        self.points.clear()
        self.is_complete = False
    
    def optimize_zone(self):
        if len(self.points) < 3:
            return
        pts = np.array(self.points, dtype=np.float32)
        hull = cv2.convexHull(pts)
        self.points = [tuple(map(int, p[0])) for p in hull]
    
    def contains_point(self, x: int, y: int) -> bool:
        if not self.is_complete or len(self.points) < 3:
            return False
        pts = np.array(self.points, dtype=np.int32)
        return cv2.pointPolygonTest(pts, (float(x), float(y)), False) >= 0
    
    def draw(self, frame: np.ndarray, breach: bool = False) -> np.ndarray:
        if not self.points:
            return frame
        
        h, w = frame.shape[:2]
        
        self.animation_phase = (self.animation_phase + 0.08) % (2 * math.pi)
        self.scan_offset = (self.scan_offset + 0.015) % 1.0
        pulse = (math.sin(self.animation_phase) + 1) / 2
        
        main_color = (0, 0, 255) if breach else self.color
        fill_alpha = 0.3 if breach else 0.12
        
        pts = np.array(self.points, dtype=np.int32)
        
        if self.is_complete and len(self.points) >= 3:
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], main_color)
            cv2.addWeighted(overlay, fill_alpha, frame, 1 - fill_alpha, 0, frame)
            
            self._draw_grid(frame, pts, main_color, h, w)
            self._draw_walls(frame, main_color, pulse, h)
            
            thickness = int(2 + pulse * 2)
            cv2.polylines(frame, [pts], True, main_color, thickness, cv2.LINE_AA)
            
            self._draw_scan(frame, pts, pulse, h, w)
            self._draw_label(frame, breach)
        
        for pt in self.points:
            r = int(5 + 2 * pulse)
            cv2.circle(frame, pt, r, main_color, -1)
            cv2.circle(frame, pt, r, (255, 255, 255), 1)
        
        return frame
    
    def _draw_grid(self, frame, pts, color, h, w):
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(mask, [pts], 255)
        
        x_min = max(0, int(pts[:, 0].min()))
        x_max = min(w - 1, int(pts[:, 0].max()))
        y_min = max(0, int(pts[:, 1].min()))
        y_max = min(h - 1, int(pts[:, 1].max()))
        
        grid_color = tuple(c // 3 for c in color)
        
        for y in range(y_min, y_max + 1, self.grid_spacing):
            if 0 <= y < h:
                row = mask[y, x_min:x_max+1]
                indices = np.where(row > 0)[0]
                if len(indices) >= 2:
                    cv2.line(frame, (x_min + indices[0], y), (x_min + indices[-1], y), grid_color, 1)
    
    def _draw_walls(self, frame, color, pulse, h):
        if len(self.points) < 3:
            return
        
        wall_h = int(self.zone_height * (0.7 + 0.3 * pulse))
        
        for i, pt in enumerate(self.points):
            ratio = pt[1] / max(1, h)
            persp = 1.0 - ratio * 0.3
            top = (pt[0], pt[1] - int(wall_h * persp))
            cv2.line(frame, pt, top, color, 1)
            
            next_i = (i + 1) % len(self.points)
            next_pt = self.points[next_i]
            next_ratio = next_pt[1] / max(1, h)
            next_persp = 1.0 - next_ratio * 0.3
            next_top = (next_pt[0], next_pt[1] - int(wall_h * next_persp))
            cv2.line(frame, top, next_top, color, 1)
    
    def _draw_scan(self, frame, pts, pulse, h, w):
        if len(pts) < 3:
            return
        
        y_min = max(0, int(pts[:, 1].min()))
        y_max = min(h - 1, int(pts[:, 1].max()))
        
        if y_max <= y_min:
            return
        
        scan_y = int(y_min + (y_max - y_min) * self.scan_offset)
        scan_y = max(y_min, min(y_max, scan_y))
        
        if scan_y < 0 or scan_y >= h:
            return
        
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(mask, [pts], 255)
        
        row = mask[scan_y, :]
        indices = np.where(row > 0)[0]
        
        if len(indices) >= 2:
            x_start, x_end = indices[0], indices[-1]
            for x in range(x_start, x_end + 1):
                intensity = int(150 * pulse)
                cv2.circle(frame, (x, scan_y), 1, (0, intensity, intensity), -1)
    
    def _draw_label(self, frame, breach):
        if not self.points:
            return
        
        cx = sum(p[0] for p in self.points) // len(self.points)
        cy = sum(p[1] for p in self.points) // len(self.points)
        
        label = f"{self.name}: BREACH!" if breach else self.name
        color = (0, 0, 255) if breach else self.color
        
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (cx - tw//2 - 5, cy - th - 5), (cx + tw//2 + 5, cy + 5), (0, 0, 0), -1)
        cv2.putText(frame, label, (cx - tw//2, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


class MultiZoneManager:
    def __init__(self):
        self.zones: List[DetectionZone3D] = []
        self.active_index: int = -1
        self.colors = [(0, 255, 255), (255, 0, 255), (0, 255, 0), (255, 165, 0)]
    
    def create_zone(self, name: str = None) -> DetectionZone3D:
        idx = len(self.zones) + 1
        zone = DetectionZone3D(
            zone_id=idx,
            name=name or f"Zone {idx}",
            color=self.colors[(idx - 1) % len(self.colors)]
        )
        self.zones.append(zone)
        self.active_index = len(self.zones) - 1
        return zone
    
    def get_active_zone(self) -> Optional[DetectionZone3D]:
        if 0 <= self.active_index < len(self.zones):
            return self.zones[self.active_index]
        return None
    
    def get_zone_count(self) -> int:
        return len(self.zones)
    
    def delete_all_zones(self):
        self.zones.clear()
        self.active_index = -1
    
    def check_all_zones(self, x: int, y: int) -> List[DetectionZone3D]:
        return [z for z in self.zones if z.is_complete and z.contains_point(x, y)]
    
    def draw_all(self, frame: np.ndarray, breached_ids: List[int] = None) -> np.ndarray:
        breached_ids = breached_ids or []
        for zone in self.zones:
            frame = zone.draw(frame, zone.zone_id in breached_ids)
        return frame


class CornerDetector:
    @staticmethod
    def detect_floor_corners(frame: np.ndarray) -> List[Tuple[int, int]]:
        if frame is None or frame.size == 0:
            return []
        
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        
        corners = []
        pts = cv2.goodFeaturesToTrack(gray, maxCorners=50, qualityLevel=0.01, minDistance=50)
        if pts is not None:
            for pt in pts:
                x, y = pt.ravel()
                if y > h * 0.4:
                    corners.append((int(x), int(y)))
        
        if corners:
            corners = CornerDetector._cluster(corners, 50)
            corners = CornerDetector._sort_clockwise(corners)
        
        return corners[:6]
    
    @staticmethod
    def _cluster(points, threshold=50):
        if not points:
            return []
        
        clusters = []
        used = set()
        
        for i, p1 in enumerate(points):
            if i in used:
                continue
            
            cluster = [p1]
            used.add(i)
            
            for j, p2 in enumerate(points):
                if j not in used:
                    dist = math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)
                    if dist < threshold:
                        cluster.append(p2)
                        used.add(j)
            
            avg_x = sum(p[0] for p in cluster) // len(cluster)
            avg_y = sum(p[1] for p in cluster) // len(cluster)
            clusters.append((avg_x, avg_y))
        
        return clusters
    
    @staticmethod
    def _sort_clockwise(points):
        if len(points) < 3:
            return points
        
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        
        return sorted(points, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
