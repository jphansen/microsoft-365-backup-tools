#!/usr/bin/env python3
"""
Checksum Database for Incremental SharePoint Backup
Manages SQLite database to track file checksums and backup history.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import hashlib

logger = logging.getLogger(__name__)


class BackupChecksumDB:
    """SQLite database for tracking file checksums and backup history."""
    
    def __init__(self, db_path: str = "backup_checksums.db"):
        """
        Initialize checksum database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create backup_files table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS backup_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    last_modified TIMESTAMP,
                    checksum_sha256 TEXT,
                    backup_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1,
                    UNIQUE(site_id, file_path)
                )
            ''')
            
            # Create backup_history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS backup_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_type TEXT NOT NULL,  -- 'full', 'incremental', 'verify'
                    site_id TEXT,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    files_backed_up INTEGER DEFAULT 0,
                    files_skipped INTEGER DEFAULT 0,
                    total_size BIGINT DEFAULT 0,
                    status TEXT DEFAULT 'completed',  -- 'completed', 'failed', 'partial'
                    error_message TEXT
                )
            ''')
            
            # Create file_history table for version tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS file_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER,
                    version INTEGER,
                    checksum_sha256 TEXT,
                    file_size INTEGER,
                    last_modified TIMESTAMP,
                    backup_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_id) REFERENCES backup_files (id)
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_file ON backup_files (site_id, file_path)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_checksum ON backup_files (checksum_sha256)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_backup_time ON backup_history (start_time)')
            
            conn.commit()
        
        logger.info(f"Checksum database initialized: {self.db_path}")
    
    def get_file_record(self, site_id: str, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get file record from database.
        
        Args:
            site_id: SharePoint site ID
            file_path: File path within SharePoint
            
        Returns:
            Dictionary with file record or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM backup_files 
                WHERE site_id = ? AND file_path = ?
            ''', (site_id, file_path))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def update_file_record(self, site_id: str, file_path: str, file_name: str, 
                          file_size: int, last_modified: str, checksum: str) -> int:
        """
        Update or insert file record in database.
        
        Args:
            site_id: SharePoint site ID
            file_path: File path within SharePoint
            file_name: File name
            file_size: File size in bytes
            last_modified: Last modified timestamp
            checksum: SHA-256 checksum
            
        Returns:
            File ID in database
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if file exists
            cursor.execute('''
                SELECT id, version FROM backup_files 
                WHERE site_id = ? AND file_path = ?
            ''', (site_id, file_path))
            
            existing = cursor.fetchone()
            
            if existing:
                file_id, version = existing
                
                # Archive old version to history
                cursor.execute('''
                    INSERT INTO file_history (file_id, version, checksum_sha256, file_size, last_modified)
                    SELECT id, version, checksum_sha256, file_size, last_modified
                    FROM backup_files WHERE id = ?
                ''', (file_id,))
                
                # Update file record with new version
                cursor.execute('''
                    UPDATE backup_files 
                    SET file_name = ?, file_size = ?, last_modified = ?, 
                        checksum_sha256 = ?, backup_timestamp = CURRENT_TIMESTAMP,
                        version = version + 1
                    WHERE id = ?
                ''', (file_name, file_size, last_modified, checksum, file_id))
                
                logger.debug(f"Updated file record: {file_path} (v{version + 1})")
                return file_id
            else:
                # Insert new file record
                cursor.execute('''
                    INSERT INTO backup_files 
                    (site_id, file_path, file_name, file_size, last_modified, checksum_sha256)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (site_id, file_path, file_name, file_size, last_modified, checksum))
                
                file_id = cursor.lastrowid
                logger.debug(f"Created new file record: {file_path} (id: {file_id})")
                return file_id
    
    def is_file_unchanged(self, site_id: str, file_path: str, 
                         current_checksum: str, current_size: int) -> Tuple[bool, Optional[Dict]]:
        """
        Check if file has changed since last backup.
        
        Args:
            site_id: SharePoint site ID
            file_path: File path within SharePoint
            current_checksum: Current SHA-256 checksum
            current_size: Current file size
            
        Returns:
            Tuple of (is_unchanged, file_record)
        """
        record = self.get_file_record(site_id, file_path)
        
        if not record:
            return False, None  # File not in database, needs backup
        
        # Quick check: size changed?
        if current_size != record['file_size']:
            return False, record
        
        # Deep check: checksum changed?
        if current_checksum != record['checksum_sha256']:
            return False, record
        
        # File unchanged
        return True, record
    
    def start_backup_session(self, backup_type: str, site_id: str = None) -> int:
        """
        Start a new backup session and return session ID.
        
        Args:
            backup_type: 'full', 'incremental', or 'verify'
            site_id: Optional site ID for site-specific backup
            
        Returns:
            Backup session ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO backup_history (backup_type, site_id, start_time, status)
                VALUES (?, ?, CURRENT_TIMESTAMP, 'running')
            ''', (backup_type, site_id))
            
            session_id = cursor.lastrowid
            logger.info(f"Started backup session {session_id} ({backup_type})")
            return session_id
    
    def update_backup_session(self, session_id: int, files_backed_up: int = 0, 
                             files_skipped: int = 0, total_size: int = 0,
                             status: str = 'completed', error_message: str = None):
        """
        Update backup session with results.
        
        Args:
            session_id: Backup session ID
            files_backed_up: Number of files backed up
            files_skipped: Number of files skipped (unchanged)
            total_size: Total size of backed up files in bytes
            status: 'completed', 'failed', or 'partial'
            error_message: Error message if failed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE backup_history 
                SET end_time = CURRENT_TIMESTAMP,
                    files_backed_up = ?,
                    files_skipped = ?,
                    total_size = ?,
                    status = ?,
                    error_message = ?
                WHERE id = ?
            ''', (files_backed_up, files_skipped, total_size, status, error_message, session_id))
            
            logger.info(f"Updated backup session {session_id}: "
                       f"{files_backed_up} backed up, {files_skipped} skipped, "
                       f"{total_size:,} bytes, status: {status}")
    
    def get_backup_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Get backup statistics for the last N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dictionary with backup statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get overall stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_backups,
                    SUM(files_backed_up) as total_files_backed_up,
                    SUM(files_skipped) as total_files_skipped,
                    SUM(total_size) as total_size_backed_up,
                    AVG(files_backed_up) as avg_files_per_backup
                FROM backup_history 
                WHERE status = 'completed' 
                AND start_time > datetime('now', ?)
            ''', (f'-{days} days',))
            
            stats = dict(cursor.fetchone())
            
            # Get backup type distribution
            cursor.execute('''
                SELECT backup_type, COUNT(*) as count
                FROM backup_history 
                WHERE status = 'completed' 
                AND start_time > datetime('now', ?)
                GROUP BY backup_type
            ''', (f'-{days} days',))
            
            stats['backup_types'] = {row['backup_type']: row['count'] for row in cursor.fetchall()}
            
            # Get recent backups
            cursor.execute('''
                SELECT * FROM backup_history 
                WHERE status = 'completed'
                ORDER BY start_time DESC 
                LIMIT 10
            ''')
            
            stats['recent_backups'] = [dict(row) for row in cursor.fetchall()]
            
            return stats
    
    def cleanup_old_records(self, keep_days: int = 90):
        """
        Clean up old backup records.
        
        Args:
            keep_days: Keep records newer than this many days
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Count records to be deleted
            cursor.execute('''
                SELECT COUNT(*) FROM backup_history 
                WHERE start_time < datetime('now', ?)
            ''', (f'-{keep_days} days',))
            
            count = cursor.fetchone()[0]
            
            if count > 0:
                # Delete old backup history
                cursor.execute('''
                    DELETE FROM backup_history 
                    WHERE start_time < datetime('now', ?)
                ''', (f'-{keep_days} days',))
                
                # Delete orphaned file history
                cursor.execute('''
                    DELETE FROM file_history 
                    WHERE file_id NOT IN (SELECT id FROM backup_files)
                ''')
                
                logger.info(f"Cleaned up {count} old backup records (older than {keep_days} days)")
                conn.commit()
            else:
                logger.info(f"No old records to clean up (keeping {keep_days} days)")
    
    def export_to_json(self, output_path: str):
        """
        Export database to JSON file for backup/analysis.
        
        Args:
            output_path: Path to output JSON file
        """
        data = {
            'export_timestamp': datetime.now().isoformat(),
            'database_path': str(self.db_path),
            'backup_files': [],
            'backup_history': []
        }
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Export backup_files
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM backup_files ORDER BY site_id, file_path')
            data['backup_files'] = [dict(row) for row in cursor.fetchall()]
            
            # Export backup_history
            cursor.execute('SELECT * FROM backup_history ORDER BY start_time DESC')
            data['backup_history'] = [dict(row) for row in cursor.fetchall()]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Exported database to {output_path} "
                   f"({len(data['backup_files'])} files, {len(data['backup_history'])} backups)")


def calculate_checksum(file_path: Path) -> str:
    """
    Calculate SHA-256 checksum of a local file.
    
    Args:
        file_path: Path to local file
        
    Returns:
        SHA-256 checksum as hex string
    """
    sha256_hash = hashlib.sha256()
    
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate checksum for {file_path}: {str(e)}")
        raise


def calculate_stream_checksum(data_stream, chunk_size: int = 4096) -> str:
    """
    Calculate SHA-256 checksum from a data stream.
    
    Args:
        data_stream: Iterable yielding bytes chunks
        chunk_size: Size of chunks to process
        
    Returns:
        SHA-256 checksum as hex string
    """
    sha256_hash = hashlib.sha256()
    
    try:
        for chunk in data_stream:
            if isinstance(chunk, bytes):
                sha256_hash.update(chunk)
            else:
                sha256_hash.update(chunk.encode('utf-8'))
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate stream checksum: {str(e)}")
        raise


if __name__ == "__main__":
    # Test the database module
    import sys
    logging.basicConfig(level=logging.INFO)
    
    db = BackupChecksumDB("test_checksums.db")
    
    # Test file record operations
    file_id = db.update_file_record(
        site_id="test_site",
        file_path="/documents/test.docx",
        file_name="test.docx",
        file_size=1024,
        last_modified="2024-01-01T12:00:00Z",
        checksum="abc123"
    )
    
    print(f"Created file record with ID: {file_id}")
    
    # Test unchanged check
    unchanged, record = db.is_file_unchanged(
        site_id="test_site",
        file_path="/documents/test.docx",
        current_checksum="abc123",
        current_size=1024
    )
    
    print(f"File unchanged: {unchanged}")
    
    # Test backup session
    session_id = db.start_backup_session("incremental", "test_site")
    db.update_backup_session(session_id, files_backed_up=10, files_skipped=5, total_size=10240)
    
    # Get stats
    stats = db.get_backup_stats(7)
    print(f"Backup stats: {stats}")
    
    print("✅ Checksum database module test completed")