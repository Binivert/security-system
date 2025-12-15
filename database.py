#!/usr/bin/env python3
"""Database module - SQLite with connection pooling."""

import sqlite3
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
from contextlib import contextmanager

from config import Config


class DatabaseManager:
    """Database manager with connection pooling."""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH
        self._local = threading.local()
        self._lock = threading.Lock()
        
        # Initialize database
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    @contextmanager
    def _cursor(self):
        """Context manager for cursor."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def _init_db(self):
        """Initialize database tables."""
        with self._cursor() as cursor:
            # Events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT NOT NULL,
                    description TEXT,
                    image_path TEXT,
                    person_count INTEGER DEFAULT 0,
                    zone_id INTEGER,
                    confidence REAL
                )
            """)
            
            # Daily stats table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date DATE PRIMARY KEY,
                    alerts INTEGER DEFAULT 0,
                    breaches INTEGER DEFAULT 0,
                    persons_detected INTEGER DEFAULT 0,
                    recording_minutes INTEGER DEFAULT 0
                )
            """)
            
            # Faces table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS faces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    image_path TEXT,
                    added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_seen DATETIME,
                    seen_count INTEGER DEFAULT 0
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
    
    def log_event(self, event_type: str, description: str = "",
                  image_path: Optional[str] = None, person_count: int = 0,
                  zone_id: Optional[int] = None, confidence: Optional[float] = None):
        """Log an event."""
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT INTO events (event_type, description, image_path, person_count, zone_id, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event_type, description, image_path, person_count, zone_id, confidence))
    
    def get_recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent events."""
        with self._cursor() as cursor:
            cursor.execute("""
                SELECT * FROM events
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_events_by_type(self, event_type: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get events by type."""
        with self._cursor() as cursor:
            cursor.execute("""
                SELECT * FROM events
                WHERE event_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (event_type, limit))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_events_in_range(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        """Get events in date range."""
        with self._cursor() as cursor:
            cursor.execute("""
                SELECT * FROM events
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp DESC
            """, (start.isoformat(), end.isoformat()))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_daily_stats(self, alerts: int = 0, breaches: int = 0,
                           persons: int = 0, recording_mins: int = 0):
        """Update daily statistics."""
        today = datetime.now().date().isoformat()
        
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT INTO daily_stats (date, alerts, breaches, persons_detected, recording_minutes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    alerts = alerts + excluded.alerts,
                    breaches = breaches + excluded.breaches,
                    persons_detected = persons_detected + excluded.persons_detected,
                    recording_minutes = recording_minutes + excluded.recording_minutes
            """, (today, alerts, breaches, persons, recording_mins))
    
    def get_daily_stats(self, date: Optional[str] = None) -> Dict[str, int]:
        """Get daily statistics."""
        if date is None:
            date = datetime.now().date().isoformat()
        
        with self._cursor() as cursor:
            cursor.execute("""
                SELECT * FROM daily_stats WHERE date = ?
            """, (date,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return {'date': date, 'alerts': 0, 'breaches': 0, 'persons_detected': 0, 'recording_minutes': 0}
    
    def get_weekly_stats(self) -> List[Dict[str, Any]]:
        """Get stats for the last 7 days."""
        with self._cursor() as cursor:
            cursor.execute("""
                SELECT * FROM daily_stats
                WHERE date >= date('now', '-7 days')
                ORDER BY date DESC
            """)
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_face_seen(self, name: str):
        """Update last seen time for a face."""
        with self._cursor() as cursor:
            cursor.execute("""
                UPDATE faces
                SET last_seen = CURRENT_TIMESTAMP, seen_count = seen_count + 1
                WHERE name = ?
            """, (name,))
    
    def add_face(self, name: str, image_path: Optional[str] = None):
        """Add a new trusted face."""
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT OR IGNORE INTO faces (name, image_path)
                VALUES (?, ?)
            """, (name, image_path))
    
    def get_faces(self) -> List[Dict[str, Any]]:
        """Get all trusted faces."""
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM faces ORDER BY name")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def cleanup_old_events(self, days: int = 30):
        """Delete events older than specified days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self._cursor() as cursor:
            cursor.execute("""
                DELETE FROM events WHERE timestamp < ?
            """, (cutoff,))
            
            deleted = cursor.rowcount
            if deleted > 0:
                print(f"[DB] Cleaned up {deleted} old events")
    
    def get_event_count(self, event_type: Optional[str] = None) -> int:
        """Get total event count."""
        with self._cursor() as cursor:
            if event_type:
                cursor.execute("SELECT COUNT(*) FROM events WHERE event_type = ?", (event_type,))
            else:
                cursor.execute("SELECT COUNT(*) FROM events")
            
            return cursor.fetchone()[0]
