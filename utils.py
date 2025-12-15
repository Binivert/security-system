#!/usr/bin/env python3
"""Utilities - 3D Holographic Zone with Scanning Animation."""

import cv2
import numpy as np
from typing import List, Tuple, Optional
import time
import math


class HolographicZone3D:
    """3D holographic zone with scanning animation."""
    
    _id_counter = 0
    
    def __init__(self, name: str = "Zone"):
        HolographicZone3D._id_counter += 1
        self.zone_id = HolographicZone3D._id_counter
        self.name = name
        self.points: List[Tuple[int, int]] = []
        self.is_complete = False
        self.is_active = True
        
        # Animation state
        self.scan_position = 0.0  # 0.0 to 1.0
        self.scan_direction = 1
        self.last_update = time.time()
        self.pulse_phase = 0.0
        self.corner_rotation = 0.0
        
        # Colors
        self.color_normal = (255, 255, 0)  # Cyan
        self.color_breach = (0, 0, 255)    # Red
        self.color_scan = (255, 200, 0)    # Bright cyan
        self.color_grid = (255, 150, 0)    # Darker cyan
    
    def add_point(self, x: int, y: int):
        """Add a point to the zone."""
        self.points.append((x, y))
        if len(self.points) >= 3:
            self.is_complete = True
    
    def contains_point(self, x: int, y: int) -> bool:
        """Check if point is inside zone using ray casting."""
        if not self.is_complete or len(self.points) < 3:
            return False
        
        n = len(self.points)
        inside = False
        
        j = n - 1
        for i in range(n):
            xi, yi = self.points[i]
            xj, yj = self.points[j]
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        
        return inside
    
    def update_animation(self):
        """Update animation state."""
        now = time.time()
        dt = now - self.last_update
        self.last_update = now
        
        # Update scan line position
        self.scan_position += dt * 0.5 * self.scan_direction
        if self.scan_position >= 1.0:
            self.scan_position = 1.0
            self.scan_direction = -1
        elif self.scan_position <= 0.0:
            self.scan_position = 0.0
            self.scan_direction = 1
        
        # Update pulse phase
        self.pulse_phase = (self.pulse_phase + dt * 3.0) % (2 * math.pi)
        
        # Update corner rotation
        self.corner_rotation = (self.corner_rotation + dt * 90) % 360
    
    def draw(self, frame: np.ndarray, is_breached: bool = False, is_armed: bool = True) -> np.ndarray:
        """Draw 3D holographic zone with scanning animation."""
        if not self.is_complete or len(self.points) < 3:
            # Draw incomplete zone
            for i, pt in enumerate(self.points):
                cv2.circle(frame, pt, 8, (0, 255, 255), 2)
                if i > 0:
                    cv2.line(frame, self.points[i-1], pt, (0, 255, 255), 2)
            return frame
        
        self.update_animation()
        
        # Choose colors based on state
        if is_breached:
            main_color = self.color_breach
            scan_color = (100, 100, 255)
            grid_color = (50, 50, 200)
            text = "!! BREACH !!"
        else:
            main_color = self.color_normal
            scan_color = self.color_scan
            grid_color = self.color_grid
            text = "SCANNING" if is_armed else "ZONE"
        
        pts = np.array(self.points, dtype=np.int32)
        
        # Calculate bounding box
        min_x = min(p[0] for p in self.points)
        max_x = max(p[0] for p in self.points)
        min_y = min(p[1] for p in self.points)
        max_y = max(p[1] for p in self.points)
        
        # Create overlay for transparency
        overlay = frame.copy()
        
        # 1. Draw semi-transparent fill with 3D gradient
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [pts], 255)
        
        # Create gradient for 3D effect (darker at top, lighter at bottom)
        for y in range(min_y, max_y):
            alpha = (y - min_y) / max(1, max_y - min_y)
            row_color = (
                int(main_color[0] * (0.1 + 0.15 * alpha)),
                int(main_color[1] * (0.1 + 0.15 * alpha)),
                int(main_color[2] * (0.1 + 0.15 * alpha))
            )
            cv2.line(overlay, (min_x, y), (max_x, y), row_color, 1)
        
        # Apply mask
        mask_3ch = cv2.merge([mask, mask, mask])
        overlay = np.where(mask_3ch > 0, overlay, frame)
        frame = cv2.addWeighted(overlay, 0.5, frame, 0.5, 0)
        
        # 2. Draw grid pattern for 3D depth effect
        grid_spacing = 30
        grid_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.fillPoly(grid_mask, [pts], 255)
        
        # Horizontal grid lines with perspective
        for y in range(min_y, max_y, grid_spacing):
            # Perspective: lines get closer together toward top
            perspective_factor = 0.5 + 0.5 * ((y - min_y) / max(1, max_y - min_y))
            thickness = max(1, int(perspective_factor * 1.5))
            cv2.line(frame, (min_x, y), (max_x, y), grid_color, thickness)
        
        # Vertical grid lines
        for x in range(min_x, max_x, grid_spacing):
            cv2.line(frame, (x, min_y), (x, max_y), grid_color, 1)
        
        # Mask grid to zone
        # (grid is already drawn, just for visual effect)
        
        # 3. Draw scanning line
        if is_armed:
            scan_y = int(min_y + (max_y - min_y) * self.scan_position)
            
            # Find intersection points with zone edges at scan_y
            intersections = []
            n = len(self.points)
            for i in range(n):
                p1 = self.points[i]
                p2 = self.points[(i + 1) % n]
                
                if (p1[1] <= scan_y <= p2[1]) or (p2[1] <= scan_y <= p1[1]):
                    if p1[1] != p2[1]:
                        t = (scan_y - p1[1]) / (p2[1] - p1[1])
                        x = int(p1[0] + t * (p2[0] - p1[0]))
                        intersections.append(x)
            
            if len(intersections) >= 2:
                intersections.sort()
                x1, x2 = intersections[0], intersections[-1]
                
                # Draw scan line with glow
                cv2.line(frame, (x1, scan_y), (x2, scan_y), (scan_color[0]//2, scan_color[1]//2, scan_color[2]//2), 8)
                cv2.line(frame, (x1, scan_y), (x2, scan_y), scan_color, 4)
                cv2.line(frame, (x1, scan_y), (x2, scan_y), (255, 255, 255), 1)
        
        # 4. Draw glowing edges with pulse effect
        pulse = 0.7 + 0.3 * math.sin(self.pulse_phase)
        edge_color = (
            int(main_color[0] * pulse),
            int(main_color[1] * pulse),
            int(main_color[2] * pulse)
        )
        
        # Outer glow
        cv2.polylines(frame, [pts], True, (edge_color[0]//3, edge_color[1]//3, edge_color[2]//3), 6)
        # Main edge
        cv2.polylines(frame, [pts], True, edge_color, 3)
        # Inner highlight
        cv2.polylines(frame, [pts], True, (255, 255, 255), 1)
        
        # 5. Draw animated corner markers
        corner_size = 20
        for i, pt in enumerate(self.points):
            # Calculate rotation offset for this corner
            angle = math.radians(self.corner_rotation + i * 90)
            
            # Draw rotating corner bracket
            dx1 = int(corner_size * math.cos(angle))
            dy1 = int(corner_size * math.sin(angle))
            dx2 = int(corner_size * math.cos(angle + math.pi/2))
            dy2 = int(corner_size * math.sin(angle + math.pi/2))
            
            # Corner lines
            cv2.line(frame, pt, (pt[0] + dx1, pt[1] + dy1), main_color, 2)
            cv2.line(frame, pt, (pt[0] + dx2, pt[1] + dy2), main_color, 2)
            
            # Corner circle
            cv2.circle(frame, pt, 6, main_color, -1)
            cv2.circle(frame, pt, 8, (255, 255, 255), 1)
        
        # 6. Draw status text with blinking effect
        center_x = (min_x + max_x) // 2
        center_y = (min_y + max_y) // 2
        
        # Blinking for armed state
        show_text = True
        if is_armed and not is_breached:
            show_text = int(time.time() * 2) % 2 == 0
        
        if show_text:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.7
            thickness = 2
            
            (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
            text_x = center_x - tw // 2
            text_y = min_y - 15
            
            # Text background
            cv2.rectangle(frame, (text_x - 5, text_y - th - 5), (text_x + tw + 5, text_y + 5), (0, 0, 0), -1)
            cv2.rectangle(frame, (text_x - 5, text_y - th - 5), (text_x + tw + 5, text_y + 5), main_color, 1)
            
            # Text
            cv2.putText(frame, text, (text_x, text_y), font, font_scale, main_color, thickness)
        
        # 7. Draw zone name
        name_text = f"{self.name} #{self.zone_id}"
        cv2.putText(frame, name_text, (min_x, max_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, main_color, 1)
        
        return frame
    
    def clear(self):
        """Clear zone points."""
        self.points.clear()
        self.is_complete = False


class MultiZoneManager:
    """Manage multiple holographic zones."""
    
    def __init__(self):
        self.zones: List[HolographicZone3D] = []
        self.active_zone_idx = -1
        self.is_armed = False
    
    def create_zone(self, name: str = "Zone") -> HolographicZone3D:
        """Create a new zone."""
        zone = HolographicZone3D(name)
        self.zones.append(zone)
        self.active_zone_idx = len(self.zones) - 1
        return zone
    
    def get_active_zone(self) -> Optional[HolographicZone3D]:
        """Get currently active zone."""
        if 0 <= self.active_zone_idx < len(self.zones):
            return self.zones[self.active_zone_idx]
        return None
    
    def check_all_zones(self, x: int, y: int) -> bool:
        """Check if point is in any zone."""
        for zone in self.zones:
            if zone.is_complete and zone.contains_point(x, y):
                return True
        return False
    
    def get_zone_count(self) -> int:
        """Get number of complete zones."""
        return sum(1 for z in self.zones if z.is_complete)
    
    def delete_all_zones(self):
        """Delete all zones."""
        self.zones.clear()
        self.active_zone_idx = -1
        HolographicZone3D._id_counter = 0
    
    def draw_all(self, frame: np.ndarray, breached_ids: List[int] = None, is_armed: bool = True) -> np.ndarray:
        """Draw all zones with 3D holographic effect."""
        if breached_ids is None:
            breached_ids = []
        
        self.is_armed = is_armed
        
        for zone in self.zones:
            is_breached = zone.zone_id in breached_ids
            frame = zone.draw(frame, is_breached, is_armed)
        
        return frame


class CornerDetector:
    """Detect corners for auto zone creation."""
    
    def detect_floor_corners(self, frame: np.ndarray) -> List[Tuple[int, int]]:
        """Detect floor corners using edge detection."""
        if frame is None:
            return []
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        
        edges = cv2.Canny(gray, 50, 150)
        
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=100, maxLineGap=10)
        
        if lines is None:
            return []
        
        corners = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            corners.append((x1, y1))
            corners.append((x2, y2))
        
        if len(corners) < 4:
            return []
        
        corners = list(set(corners))
        
        h, w = frame.shape[:2]
        filtered = [(x, y) for x, y in corners if y > h * 0.3]
        
        if len(filtered) < 3:
            return corners[:4] if len(corners) >= 4 else []
        
        return filtered[:8]
