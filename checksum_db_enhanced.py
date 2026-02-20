#!/usr/bin/env python3
"""
Enhanced Checksum Database with eTag/cTag Support
Extends the original checksum database to store Microsoft Graph API metadata
for optimized change detection.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import hashlib

logger = logging.getLogger(__name__)


class EnhancedChecksumDB:
    """Enhanced SQLite database with eTag/cTag support for optimized change detection."""
    
    def __init__(self, db_path: str = "backup_checksums_enhanced.db"):
        """
        Initialize enhanced checksum database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize enhanced database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create enhanced backup_files table with eTag and cTag
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS backup_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    last_modified TIMESTAMP,
                    checksum_sha256 TEXT,
                    eTag TEXT,
                    cTag TEXT,
                    backup_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1,
                    UNIQUE(site_id, file_path)
                )
            ''')
            
            # Create backup_history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS backup_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_type TEXT NOT NULL,
                    site_id TEXT,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    files_backed_up INTEGER DEFAULT 0,
                    files_skipped INTEGER DEFAULT 0,
                    total_size BIGINT DEFAULT 0,
                    bytes_saved BIGINT DEFAULT 0,
                    status TEXT DEFAULT 'completed',
                    error_message TEXT
                )
            ''')
            
            # Create file_history table with eTag/cTag
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS file_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER,
                    version INTEGER,
                    checksum_sha256 TEXT,
                    file_size INTEGER,
                    last_modified TIMESTAMP,
                    eTag TEXT,
                    cTag TEXT,
                    backup_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_id) REFERENCES backup_files (id)
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_site_file ON backup_files (site_id, file_path)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_checksum ON backup_files (checksum_sha256)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_eTag ON backup_files (eTag)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_backup_time ON backup_history (start_time)')
            
            conn.commit()
        
        logger.info(f"Enhanced checksum database initialized: {self.db_path}")
    
    def get_file_record(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get file record from database using file_path.
        
        Args:
            file_path: Full file path (/drives/{driveId}/items/{itemId})
            
        Returns:
            Dictionary with file record or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM backup_files 
                WHERE file_path = ?
            ''', (file_path,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def update_file_record(self, site_id: str, file_path: str, file_name: str, 
                          file_size: int, last_modified: str, checksum: str,
                          eTag: str = None, cTag: str = None) -> int:
        """
        Update or insert file record with eTag/cTag metadata.
        
        Args:
            site_id: SharePoint site ID
            file_path: File path within SharePoint
            file_name: File name
            file_size: File size in bytes
            last_modified: Last modified timestamp
            checksum: SHA-256 checksum
            eTag: Microsoft Graph eTag
            cTag: Microsoft Graph cTag
            
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
                    INSERT INTO file_history (file_id, version, checksum_sha256, 
                                             file_size, last_modified, eTag, cTag)
                    SELECT id, version, checksum_sha256, file_size, last_modified, eTag, cTag
                    FROM backup_files WHERE id = ?
                ''', (file_id,))
                
                # Update file record with new version
                cursor.execute('''
                    UPDATE backup_files 
                    SET file_name = ?, file_size = ?, last_modified = ?, 
                        checksum_sha256 = ?, eTag = ?, cTag = ?,
                        backup_timestamp = CURRENT_TIMESTAMP,
                        version = version + 1
                    WHERE id = ?
                ''', (file_name, file_size, last_modified, checksum, eTag, cTag, file_id))
                
                logger.debug(f"Updated file record: {file_path} (v{version + 1})")
                return file_id
            else:
                # Insert new file record
                cursor.execute('''
                    INSERT INTO backup_files 
                    (site_id, file_path, file_name, file_size, last_modified, 
                     checksum_sha256, eTag, cTag)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (site_id, file_path, file_name, file_size, last_modified, 
                      checksum, eTag, cTag))
                
                file_id = cursor.lastrowid
                logger.debug(f"Created new file record: {file_path} (id: {file_id})")
                return file_id
    
    def is_file_unchanged_by_metadata(self, file_meta: Dict[str, Any]) -> Tuple[bool, Optional[Dict]]:
        """
        Check if file has changed using server-side metadata (eTag, size).
        
        Args:
            file_meta: Dictionary with file metadata including:
                - file_path: File path
                - eTag: Microsoft Graph eTag
                - size: File size
                
        Returns:
            Tuple of (is_unchanged, file_record)
        """
        file_path = file_meta.get('file_path')
        current_eTag = file_meta.get('eTag', '')
        current_size = file_meta.get('size', 0)
        
        record = self.get_file_record(file_path)
        
        if not record:
            return False, None  # New file
        
        # Check if eTag or size changed
        if current_eTag != record.get('eTag', '') or current_size != record.get('file_size', 0):
            return False, record
        
        # File unchanged based on metadata
        return True, record
    
    def is_file_unchanged_by_checksum(self, file_path: str, 
                                     current_checksum: str, current_size: int) -> Tuple[bool, Optional[Dict]]:
        """
        Check if file has changed using checksum (fallback method).
        
        Args:
            file_path: File path
            current_checksum: Current SHA-256 checksum
            current_size: Current file size
            
        Returns:
            Tuple of (is_unchanged, file_record)
        """
        record = self.get_file_record(file_path)
        
        if not record:
            return False, None
        
        # Quick check: size changed?
        if current_size != record.get('file_size', 0):
            return False, record
        
        # Deep check: checksum changed?
        if current_checksum != record.get('checksum_sha256', ''):
            return False, record
        
        return True, record
    
    def start_backup_session(self, backup_type: str, site_id: str = None) -> int:
        """
        Start a new backup session.
        
        Args:
            backup_type: 'full', 'incremental', or 'verify'
            site_id: Optional site ID
            
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
                             bytes_saved: int = 0, status: str = 'completed', 
                             error_message: str = None):
        """
        Update backup session with results including bytes saved.
        
        Args:
            session_id: Backup session ID
            files_backed_up: Number of files backed up
            files_skipped: Number of files skipped
            total_size: Total size of backed up files
            bytes_saved: Bytes not downloaded due to change detection
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
                    bytes_saved = ?,
                    status = ?,
                    error_message = ?
                WHERE id = ?
            ''', (files_backed_up, files_skipped, total_size, bytes_saved, 
                  status, error_message, session_id))
            
            logger.info(f"Updated backup session {session_id}: "
                       f"{files_backed_up} backed up, {files_skipped} skipped, "
                       f"{total_size:,} bytes, {bytes_saved:,} bytes saved")
    
    def get_backup_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Get enhanced backup statistics.
        
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
                    SUM(bytes_saved) as total_bytes_saved,
                    AVG(files_backed_up) as avg_files_per_backup
                FROM backup_history 
                WHERE status = 'completed' 
                AND start_time > datetime('now', ?)
            ''', (f'-{days} days',))
            
            stats = dict(cursor.fetchone())
            
            # Calculate efficiency metrics
            total_processed = stats.get('total_files_backed_up', 0) + stats.get('total_files_skipped', 0)
            if total_processed > 0:
                stats['skip_rate_percent'] = (stats.get('total_files_skipped', 0) / total_processed) * 100
                stats['efficiency_percent'] = (stats.get('total_bytes_saved', 0) / 
                                             (stats.get('total_size_backed_up', 0) + stats.get('total_bytes_saved', 0))) * 100
            
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
    
    def get_file_change_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Get statistics about file changes.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dictionary with change statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get files with multiple versions (changed files)
            cursor.execute('''
                SELECT file_id, COUNT(*) as version_count
                FROM file_history 
                WHERE backup_timestamp > datetime('now', ?)
                GROUP BY file_id
                HAVING COUNT(*) > 1
            ''', (f'-{days} days',))
            
            changed_files = [dict(row) for row in cursor.fetchall()]
            
            # Get most frequently changed files
            cursor.execute('''
                SELECT f.file_name, f.file_path, COUNT(h.id) as change_count
                FROM file_history h
                JOIN backup_files f ON h.file_id = f.id
                WHERE h.backup_timestamp > datetime('now', ?)
                GROUP BY f.id
                ORDER BY change_count DESC
                LIMIT 20
            ''', (f'-{days} days',))
            
            frequently_changed = [dict(row) for row in cursor.fetchall()]
            
            return {
                'total_changed_files': len(changed_files),
                'frequently_changed_files': frequently_changed
            }
    
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
        Export database to JSON file.
        
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
            
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM backup_files ORDER BY site_id, file_path')
            data['backup_files'] = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute('SELECT * FROM backup_history ORDER BY start_time DESC')
            data['backup_history'] = [dict(row) for row in cursor.fetchall()]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Exported database to {output_path}")


def calculate_checksum(file_path: Path) -> str:
    """Calculate SHA-256 checksum of a local file."""
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
    """Calculate SHA-256 checksum from a data stream."""
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
    # Test the enhanced database
    import sys
    logging.basicConfig(level=logging.INFO)
    
    db = EnhancedChecksumDB("test_enhanced_checksums.db")
    
    # Test file record with eTag/cTag
    file_id = db.update_file_record(
        site_id="test_site",
       