#!/usr/bin/env python3
"""
Exchange/Outlook Checksum Database Extension
Extends the existing checksum database for tracking email backups.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import hashlib

logger = logging.getLogger(__name__)


class ExchangeChecksumDB:
    """SQLite database for tracking Exchange/Outlook email checksums."""
    
    def __init__(self, db_path: str = "backup_checksums_exchange.db"):
        """
        Initialize Exchange checksum database.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema for Exchange backups."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create email_messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS email_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    folder_id TEXT,
                    folder_name TEXT,
                    subject TEXT,
                    sender TEXT,
                    received_date TIMESTAMP,
                    message_size INTEGER,
                    checksum_sha256 TEXT,
                    backup_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1,
                    has_attachments BOOLEAN DEFAULT FALSE,
                    attachment_count INTEGER DEFAULT 0,
                    backup_format TEXT DEFAULT 'both',  -- 'eml', 'json', 'both'
                    backup_path TEXT,
                    UNIQUE(user_id, message_id)
                )
            ''')
            
            # Create email_attachments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS email_attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER,
                    attachment_id TEXT,
                    attachment_name TEXT,
                    attachment_size INTEGER,
                    checksum_sha256 TEXT,
                    backup_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES email_messages (id)
                )
            ''')
            
            # Create exchange_backup_history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS exchange_backup_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_type TEXT NOT NULL,  -- 'full', 'incremental', 'verify'
                    user_id TEXT,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    emails_backed_up INTEGER DEFAULT 0,
                    emails_skipped INTEGER DEFAULT 0,
                    attachments_backed_up INTEGER DEFAULT 0,
                    attachments_skipped INTEGER DEFAULT 0,
                    total_size BIGINT DEFAULT 0,
                    status TEXT DEFAULT 'completed',  -- 'completed', 'failed', 'partial'
                    error_message TEXT
                )
            ''')
            
            # Create email_history table for version tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS email_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id INTEGER,
                    version INTEGER,
                    checksum_sha256 TEXT,
                    message_size INTEGER,
                    backup_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (email_id) REFERENCES email_messages (id)
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_message ON email_messages (user_id, message_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_checksum ON email_messages (checksum_sha256)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_received_date ON email_messages (received_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_exchange_backup_time ON exchange_backup_history (start_time)')
            
            conn.commit()
        
        logger.info(f"Exchange checksum database initialized: {self.db_path}")
    
    def get_email_record(self, user_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get email record from database.
        
        Args:
            user_id: User ID or email address
            message_id: Graph API message ID
            
        Returns:
            Dictionary with email record or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM email_messages 
                WHERE user_id = ? AND message_id = ?
            ''', (user_id, message_id))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_user_email_records(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all email records for a user.
        
        Args:
            user_id: User ID or email address
            
        Returns:
            List of email records
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM email_messages 
                WHERE user_id = ?
            ''', (user_id,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_email_record(self, user_id: str, message_id: str, folder_id: str = None,
                           folder_name: str = None, subject: str = None, sender: str = None,
                           received_date: str = None, message_size: int = 0,
                           checksum: str = None, has_attachments: bool = False,
                           attachment_count: int = 0, backup_format: str = 'both',
                           backup_path: str = None) -> int:
        """
        Update or insert email record in database.
        
        Args:
            user_id: User ID or email address
            message_id: Graph API message ID
            folder_id: Folder ID
            folder_name: Folder name
            subject: Email subject
            sender: Sender email address
            received_date: Received date/time
            message_size: Message size in bytes
            checksum: SHA-256 checksum
            has_attachments: Whether message has attachments
            attachment_count: Number of attachments
            backup_format: Backup format ('eml', 'json', 'both')
            backup_path: Path where email was backed up
            
        Returns:
            Email ID in database
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if email exists
            cursor.execute('''
                SELECT id, version FROM email_messages 
                WHERE user_id = ? AND message_id = ?
            ''', (user_id, message_id))
            
            existing = cursor.fetchone()
            
            if existing:
                email_id, version = existing
                
                # Archive old version to history
                cursor.execute('''
                    INSERT INTO email_history (email_id, version, checksum_sha256, message_size)
                    SELECT id, version, checksum_sha256, message_size
                    FROM email_messages WHERE id = ?
                ''', (email_id,))
                
                # Update email record with new version
                cursor.execute('''
                    UPDATE email_messages 
                    SET folder_id = ?, folder_name = ?, subject = ?, sender = ?,
                        received_date = ?, message_size = ?, checksum_sha256 = ?,
                        has_attachments = ?, attachment_count = ?, backup_format = ?,
                        backup_path = ?, backup_timestamp = CURRENT_TIMESTAMP,
                        version = version + 1
                    WHERE id = ?
                ''', (folder_id, folder_name, subject, sender, received_date,
                      message_size, checksum, has_attachments, attachment_count,
                      backup_format, backup_path, email_id))
                
                logger.debug(f"Updated email record: {message_id} (v{version + 1})")
                return email_id
            else:
                # Insert new email record
                cursor.execute('''
                    INSERT INTO email_messages 
                    (user_id, message_id, folder_id, folder_name, subject, sender,
                     received_date, message_size, checksum_sha256, has_attachments,
                     attachment_count, backup_format, backup_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, message_id, folder_id, folder_name, subject, sender,
                      received_date, message_size, checksum, has_attachments,
                      attachment_count, backup_format, backup_path))
                
                email_id = cursor.lastrowid
                logger.debug(f"Created new email record: {message_id} (id: {email_id})")
                return email_id
    
    def update_attachment_record(self, email_id: int, attachment_id: str,
                                attachment_name: str, attachment_size: int,
                                checksum: str = None) -> int:
        """
        Update or insert attachment record in database.
        
        Args:
            email_id: Email ID in database
            attachment_id: Graph API attachment ID
            attachment_name: Attachment filename
            attachment_size: Attachment size in bytes
            checksum: SHA-256 checksum of attachment
            
        Returns:
            Attachment record ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if attachment exists
            cursor.execute('''
                SELECT id FROM email_attachments 
                WHERE message_id = ? AND attachment_id = ?
            ''', (email_id, attachment_id))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing attachment record
                cursor.execute('''
                    UPDATE email_attachments 
                    SET attachment_name = ?, attachment_size = ?, checksum_sha256 = ?,
                        backup_timestamp = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (attachment_name, attachment_size, checksum, existing[0]))
                
                logger.debug(f"Updated attachment record: {attachment_id}")
                return existing[0]
            else:
                # Insert new attachment record
                cursor.execute('''
                    INSERT INTO email_attachments 
                    (message_id, attachment_id, attachment_name, attachment_size, checksum_sha256)
                    VALUES (?, ?, ?, ?, ?)
                ''', (email_id, attachment_id, attachment_name, attachment_size, checksum))
                
                attachment_record_id = cursor.lastrowid
                logger.debug(f"Created new attachment record: {attachment_id} (id: {attachment_record_id})")
                return attachment_record_id
    
    def is_email_unchanged(self, user_id: str, message_id: str,
                          current_checksum: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if email has changed since last backup.
        
        Args:
            user_id: User ID or email address
            message_id: Graph API message ID
            current_checksum: Current SHA-256 checksum
            
        Returns:
            Tuple of (is_unchanged, email_record)
        """
        record = self.get_email_record(user_id, message_id)
        
        if not record:
            return False, None  # Email not in database, needs backup
        
        # Check if checksum changed
        if current_checksum != record['checksum_sha256']:
            return False, record
        
        # Email unchanged
        return True, record
    
    def start_exchange_backup_session(self, backup_type: str, user_id: str = None) -> int:
        """
        Start a new Exchange backup session and return session ID.
        
        Args:
            backup_type: 'full', 'incremental', or 'verify'
            user_id: Optional user ID for user-specific backup
            
        Returns:
            Backup session ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO exchange_backup_history (backup_type, user_id, start_time, status)
                VALUES (?, ?, CURRENT_TIMESTAMP, 'running')
            ''', (backup_type, user_id))
            
            session_id = cursor.lastrowid
            logger.info(f"Started Exchange backup session {session_id} ({backup_type})")
            return session_id
    
    def update_exchange_backup_session(self, session_id: int, emails_backed_up: int = 0,
                                      emails_skipped: int = 0, attachments_backed_up: int = 0,
                                      attachments_skipped: int = 0, total_size: int = 0,
                                      status: str = 'completed', error_message: str = None):
        """
        Update Exchange backup session with results.
        
        Args:
            session_id: Backup session ID
            emails_backed_up: Number of emails backed up
            emails_skipped: Number of emails skipped (unchanged)
            attachments_backed_up: Number of attachments backed up
            attachments_skipped: Number of attachments skipped
            total_size: Total size of backed up data in bytes
            status: 'completed', 'failed', or 'partial'
            error_message: Error message if failed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE exchange_backup_history 
                SET end_time = CURRENT_TIMESTAMP,
                    emails_backed_up = ?,
                    emails_skipped = ?,
                    attachments_backed_up = ?,
                    attachments_skipped = ?,
                    total_size = ?,
                    status = ?,
                    error_message = ?
                WHERE id = ?
            ''', (emails_backed_up, emails_skipped, attachments_backed_up,
                  attachments_skipped, total_size, status, error_message, session_id))
            
            logger.info(f"Updated Exchange backup session {session_id}: "
                       f"{emails_backed_up} emails backed up, {emails_skipped} skipped, "
                       f"{attachments_backed_up} attachments backed up, {attachments_skipped} skipped, "
                       f"{total_size:,} bytes, status: {status}")
    
    def get_exchange_backup_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Get Exchange backup statistics for the last N days.
        
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
                    SUM(emails_backed_up) as total_emails_backed_up,
                    SUM(emails_skipped) as total_emails_skipped,
                    SUM(attachments_backed_up) as total_attachments_backed_up,
                    SUM(attachments_skipped) as total_attachments_skipped,
                    SUM(total_size) as total_size_backed_up,
                    AVG(emails_backed_up) as avg_emails_per_backup
                FROM exchange_backup_history 
                WHERE status = 'completed' 
                AND start_time > datetime('now', ?)
            ''', (f'-{days} days',))
            
            stats = dict(cursor.fetchone())
            
            # Get backup type distribution
            cursor.execute('''
                SELECT backup_type, COUNT(*) as count
                FROM exchange_backup_history 
                WHERE status = 'completed' 
                AND start_time > datetime('now', ?)
                GROUP BY backup_type
            ''', (f'-{days} days',))
            
            stats['backup_types'] = {row['backup_type']: row['count'] for row in cursor.fetchall()}
            
            # Get user distribution
            cursor.execute('''
                SELECT user_id, COUNT(*) as backup_count,
                       SUM(emails_backed_up) as total_emails
                FROM exchange_backup_history 
                WHERE status = 'completed' 
                AND start_time > datetime('now', ?)
                GROUP BY user_id
            ''', (f'-{days} days',))
            
            stats['user_distribution'] = [dict(row) for row in cursor.fetchall()]
            
            # Get recent backups
            cursor.execute('''
                SELECT * FROM exchange_backup_history 
                WHERE status = 'completed'
                ORDER BY start_time DESC 
                LIMIT 10
            ''')
            
            stats['recent_backups'] = [dict(row) for row in cursor.fetchall()]
            
            return stats
    
    def get_user_backup_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Get backup summary for a specific user.
        
        Args:
            user_id: User ID or email address
            
        Returns:
            Dictionary with user backup summary
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get email count
            cursor.execute('''
                SELECT COUNT(*) as total_emails,
                       COUNT(DISTINCT folder_name) as folder_count,
                       SUM(message_size) as total_size,
                       MAX(backup_timestamp) as last_backup
                FROM email_messages 
                WHERE user_id = ?
            ''', (user_id,))
            
            summary = dict(cursor.fetchone())
            
            # Get attachment count
            cursor.execute('''
                SELECT COUNT(*) as total_attachments,
                       SUM(attachment_size) as total_attachment_size
                FROM email_attachments ea
                JOIN email_messages em ON ea.message_id = em.id
                WHERE em.user_id = ?
            ''', (user_id,))
            
            attachment_stats = dict(cursor.fetchone())
            summary.update(attachment_stats)
            
            # Get folder breakdown
            cursor.execute('''
                SELECT folder_name, COUNT(*) as email_count,
                       SUM(message_size) as folder_size
                FROM email_messages 
                WHERE user_id = ?
                GROUP BY folder_name
                ORDER BY email_count DESC
            ''', (user_id,))
            
            summary['folders'] = [dict(row) for row in cursor.fetchall()]
            
            return summary
    
    def cleanup_old_records(self, keep_days: int = 90):
        """
        Clean up old Exchange backup records.
        
        Args:
            keep_days: Keep records newer than this many days
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Count records to be deleted
            cursor.execute('''
                SELECT COUNT(*) FROM exchange_backup_history 
                WHERE start_time < datetime('now', ?)
            ''', (f'-{keep_days} days',))
            
            count = cursor.fetchone()[0]
            
            if count > 0:
                # Delete old backup history
                cursor.execute('''
                    DELETE FROM exchange_backup_history 
                    WHERE start_time < datetime('now', ?)
                ''', (f'-{keep_days} days',))
                
                # Delete orphaned email history
                cursor.execute('''
                    DELETE FROM email_history 
                    WHERE email_id NOT IN (SELECT id FROM email_messages)
                ''')
                
                logger.info(f"Cleaned up {count} old Exchange backup records (older than {keep_days} days)")
                conn.commit()
            else:
                logger.info(f"No old Exchange records to clean up (keeping {keep_days} days)")
    
    def export_to_json(self, output_path: str):
        """
        Export database to JSON file for backup/analysis.
        
        Args:
            output_path: Path to output JSON file
        """
        data = {
            'export_timestamp': datetime.now().isoformat(),
            'database_path': str(self.db_path),
            'email_messages': [],
            'exchange_backup_history': []
        }
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Export email_messages
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM email_messages ORDER BY user_id, received_date DESC')
            data['email_messages'] = [dict(row) for row in cursor.fetchall()]
            
            # Export exchange_backup_history
            cursor.execute('SELECT * FROM exchange_backup_history ORDER BY start_time DESC')
            data['exchange_backup_history'] = [dict(row) for row in cursor.fetchall()]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Exported Exchange database to {output_path} "
                   f"({len(data['email_messages'])} emails, {len(data['exchange_backup_history'])} backups)")


def calculate_email_checksum(message_data: Dict[str, Any]) -> str:
    """
    Calculate SHA-256 checksum of email message data.
    
    Args:
        message_data: Dictionary with email message data
        
    Returns:
        SHA-256 checksum as hex string
    """
    # Create a stable representation for checksum calculation
    checksum_data = {
        'id': message_data.get('id'),
        'subject': message_data.get('subject', ''),
        'from': message_data.get('from', {}),
        'body': message_data.get('body', {}).get('content', ''),
        'receivedDateTime': message_data.get('receivedDateTime', ''),
        'hasAttachments': message_data.get('hasAttachments', False)
    }
    
    checksum_string = json.dumps(checksum_data, sort_keys=True)
    return hashlib.sha256(checksum_string.encode()).hexdigest()


def calculate_attachment_checksum(attachment_data: bytes) -> str:
    """
    Calculate SHA-256 checksum of attachment data.
    
    Args:
        attachment_data: Attachment content as bytes
        
    Returns:
        SHA-256 checksum as hex string
    """
    return hashlib.sha256(attachment_data).hexdigest()


if __name__ == "__main__":
    # Test the Exchange database module
    import sys
    logging.basicConfig(level=logging.INFO)
    
    db = ExchangeChecksumDB("test_exchange_checksums.db")
    
    # Test email record operations
    email_id = db.update_email_record(
        user_id="user@example.com",
        message_id="test_message_123",
        folder_id="inbox",
        folder_name="Inbox",
        subject="Test Email",
        sender="sender@example.com",
        received_date="2024-01-01T12:00:00Z",
        message_size=1024,
        checksum="abc123",
        has_attachments=False,
        attachment_count=0,
        backup_format="both",
        backup_path="/backup/user@example.com/Inbox/Test_Email_test_message_123"
    )
    
    print(f"Created email record with ID: {email_id}")
    
    # Test unchanged check
    unchanged, record = db.is_email_unchanged(
        user_id="user@example.com",
        message_id="test_message_123",
        current_checksum="abc123"
    )
    
    print(f"Email unchanged: {unchanged}")
    
    # Test attachment record
    attachment_id = db.update_attachment_record(
        email_id=email_id,
        attachment_id="att_123",
        attachment_name="document.pdf",
        attachment_size=2048,
        checksum="def456"
    )
    
    print(f"Created attachment record with ID: {attachment_id}")
    
    # Test backup session
    session_id = db.start_exchange_backup_session("incremental", "user@example.com")
    db.update_exchange_backup_session(
        session_id,
        emails_backed_up=5,
        emails_skipped=2,
        attachments_backed_up=3,
        attachments_skipped=1,
        total_size=15360
    )
    
    # Get stats
    stats = db.get_exchange_backup_stats(7)
    print(f"Exchange backup stats: {stats}")
    
    # Get user summary
    summary = db.get_user_backup_summary("user@example.com")
    print(f"User backup summary: {summary}")
    
    print("✅ Exchange checksum database module test completed")
