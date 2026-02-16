#!/usr/bin/env python3
"""
Exchange Incremental Backup Command Line Tool
Wrapper around exchange_backup.py with command-line interface similar to sharepoint_incremental_backup.py
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# Import loguru for enhanced logging
from loguru import logger

# Import the existing ExchangeBackup class
from exchange_backup import ExchangeBackup, load_config, validate_config

# Configure loguru with custom levels and formatting
# Remove default handler
logger.remove()

# Add custom levels
logger.level("TRACE", color="<cyan>", icon="🔍")
logger.level("DEBUG", color="<blue>", icon="🐛")
logger.level("INFO", color="<green>", icon="ℹ️")
logger.level("SUCCESS", color="<bold><green>", icon="✅")
logger.level("WARNING", color="<yellow>", icon="⚠️")
logger.level("ERROR", color="<red>", icon="❌")
logger.level("CRITICAL", color="<bold><red>", icon="💥")

# Add console handler with custom format
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",  # Default level
    colorize=True
)

# Add file handler for detailed logging
logger.add(
    "exchange_incremental_backup.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="TRACE",  # Log everything to file
    rotation="10 MB",  # Rotate when file reaches 10 MB
    retention="30 days",  # Keep logs for 30 days
    compression="zip"  # Compress rotated logs
)


def create_config_from_args(args):
    """
    Create configuration dictionary from command-line arguments.
    
    Args:
        args: Command-line arguments
        
    Returns:
        Configuration dictionary
    """
    config = {}
    
    # Required configuration from environment variables
    config['EXCHANGE_TENANT_ID'] = os.environ.get('EXCHANGE_TENANT_ID')
    config['EXCHANGE_CLIENT_ID'] = os.environ.get('EXCHANGE_CLIENT_ID')
    config['EXCHANGE_CLIENT_SECRET'] = os.environ.get('EXCHANGE_CLIENT_SECRET')
    
    # Backup settings from command-line arguments
    config['EXCHANGE_BACKUP_DIR'] = args.backup_dir
    config['EXCHANGE_USER_EMAIL'] = None  # Always backup all users
    config['EXCHANGE_INCLUDE_ATTACHMENTS'] = not args.no_attachments
    config['EXCHANGE_MAX_EMAILS_PER_BACKUP'] = args.max_emails
    config['EXCHANGE_PRESERVE_FOLDER_STRUCTURE'] = not args.no_folders
    config['EXCHANGE_BACKUP_FORMAT'] = args.format
    
    # Incremental backup settings
    config['EXCHANGE_INCREMENTAL_BACKUP'] = (args.type == 'incremental')
    config['EXCHANGE_CHECKSUM_DB'] = args.db_path
    
    # Graph API settings
    config['EXCHANGE_GRAPH_ENDPOINT'] = 'https://graph.microsoft.com/v1.0'
    config['EXCHANGE_BATCH_SIZE'] = 100
    config['EXCHANGE_RATE_LIMIT_DELAY'] = 0.5
    config['EXCHANGE_MAX_RETRIES'] = 3
    
    # Filtering (none by default)
    config['EXCHANGE_FILTER_DATE_FROM'] = None
    config['EXCHANGE_FILTER_DATE_TO'] = None
    config['EXCHANGE_FILTER_SENDER'] = None
    config['EXCHANGE_FILTER_SUBJECT'] = None
    config['EXCHANGE_SKIP_ALREADY_READ'] = False
    
    # Security
    config['EXCHANGE_ENCRYPT_BACKUPS'] = False
    config['EXCHANGE_ENCRYPTION_PASSWORD'] = None
    
    # Advanced settings
    config['EXCHANGE_REQUEST_TIMEOUT'] = 30
    config['EXCHANGE_MAX_ATTACHMENT_SIZE'] = 4  # MB
    
    return config


def show_backup_stats(db_path, days=30):
    """
    Show backup statistics from the checksum database.
    
    Args:
        db_path: Path to checksum database
        days: Number of days to look back
    """
    from exchange_checksum_db import ExchangeChecksumDB
    
    try:
        db = ExchangeChecksumDB(db_path)
        stats = db.get_exchange_backup_stats(days)
        
        logger.info("=" * 80)
        logger.info("📊 EXCHANGE BACKUP STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Time period: Last {days} days")
        logger.info(f"Total backups: {stats.get('total_backups', 0)}")
        logger.info(f"Total emails backed up: {stats.get('total_emails_backed_up', 0)}")
        logger.info(f"Total emails skipped: {stats.get('total_emails_skipped', 0)}")
        logger.info(f"Total attachments backed up: {stats.get('total_attachments_backed_up', 0)}")
        logger.info(f"Total attachments skipped: {stats.get('total_attachments_skipped', 0)}")
        logger.info(f"Total size backed up: {stats.get('total_size_backed_up', 0):,} bytes")
        
        if stats.get('backup_types'):
            logger.info("\nBackup type distribution:")
            for backup_type, count in stats['backup_types'].items():
                logger.info(f"  {backup_type}: {count}")
        
        if stats.get('user_distribution'):
            logger.info(f"\nUser distribution ({len(stats['user_distribution'])} users):")
            for user in stats['user_distribution'][:10]:  # Show top 10
                logger.info(f"  {user['user_id']}: {user['backup_count']} backups, {user['total_emails']} emails")
            if len(stats['user_distribution']) > 10:
                logger.info(f"  ... and {len(stats['user_distribution']) - 10} more users")
        
        if stats.get('recent_backups'):
            logger.info(f"\nRecent backups ({len(stats['recent_backups'])} most recent):")
            for backup in stats['recent_backups']:
                start_time = backup.get('start_time', 'Unknown')
                backup_type = backup.get('backup_type', 'Unknown')
                emails_backed = backup.get('emails_backed_up', 0)
                emails_skipped = backup.get('emails_skipped', 0)
                logger.info(f"  {start_time}: {backup_type} - {emails_backed} backed up, {emails_skipped} skipped")
        
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Failed to get backup statistics: {str(e)}")
        sys.exit(1)


def cleanup_old_records(db_path, keep_days):
    """
    Cleanup old backup records.
    
    Args:
        db_path: Path to checksum database
        keep_days: Keep records newer than this many days
    """
    from exchange_checksum_db import ExchangeChecksumDB
    
    try:
        db = ExchangeChecksumDB(db_path)
        db.cleanup_old_records(keep_days)
        logger.info(f"Cleaned up records older than {keep_days} days from {db_path}")
        
    except Exception as e:
        logger.error(f"Failed to cleanup old records: {str(e)}")
        sys.exit(1)


def main():
    """Main entry point with command-line arguments."""
    # Try to load environment variables from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("Loaded environment variables from .env file")
    except ImportError:
        logger.warning("python-dotenv not installed. Using system environment variables.")
    except Exception as e:
        logger.warning(f"Failed to load .env file: {str(e)}")
    
    parser = argparse.ArgumentParser(
        description='Exchange Incremental Backup with Automatic Mailbox Discovery'
    )
    
    parser.add_argument('--type', choices=['full', 'incremental'], 
                       default='incremental',
                       help='Backup type: full or incremental (default: incremental)')
    
    parser.add_argument('--backup-dir', default='backup/exchange',
                       help='Backup directory (default: backup/exchange)')
    
    parser.add_argument('--db-path', default='backup_checksums_exchange.db',
                       help='Checksum database path (default: backup_checksums_exchange.db)')
    
    parser.add_argument('--max-emails', type=int, default=0,
                       help='Maximum emails per user (0 = unlimited, default: 0)')
    
    parser.add_argument('--no-attachments', action='store_true',
                       help='Skip attachment downloads')
    
    parser.add_argument('--no-folders', action='store_true',
                       help='Do not preserve folder structure')
    
    parser.add_argument('--format', choices=['eml', 'json', 'both'], default='both',
                       help='Backup format: eml, json, or both (default: both)')
    
    parser.add_argument('--stats', action='store_true',
                       help='Show backup statistics')
    
    parser.add_argument('--cleanup', type=int, metavar='DAYS',
                       help='Cleanup records older than N days')
    
    args = parser.parse_args()
    
    # Validate environment variables
    if not os.environ.get('EXCHANGE_TENANT_ID'):
        logger.error("Please configure Exchange credentials!")
        logger.error("Set the following environment variables:")
        logger.error("  EXCHANGE_TENANT_ID - Azure AD Tenant ID")
        logger.error("  EXCHANGE_CLIENT_ID - Azure AD App Client ID")
        logger.error("  EXCHANGE_CLIENT_SECRET - Azure AD App Client Secret")
        logger.error("Example: export EXCHANGE_TENANT_ID='your-tenant-id'")
        sys.exit(1)
    
    if not os.environ.get('EXCHANGE_CLIENT_ID') or not os.environ.get('EXCHANGE_CLIENT_SECRET'):
        logger.error("Missing EXCHANGE_CLIENT_ID or EXCHANGE_CLIENT_SECRET environment variables")
        sys.exit(1)
    
    try:
        if args.stats:
            # Show backup statistics
            show_backup_stats(args.db_path)
        elif args.cleanup:
            # Cleanup old records
            cleanup_old_records(args.db_path, args.cleanup)
        else:
            # Run backup
            logger.info("=" * 80)
            logger.info(f"Starting {args.type.upper()} tenant-wide Exchange backup")
            logger.info("=" * 80)
            logger.info(f"Backup type: {args.type}")
            logger.info(f"Backup directory: {args.backup_dir}")
            logger.info(f"Database: {args.db_path}")
            max_emails_display = "unlimited" if args.max_emails == 0 else f"{args.max_emails}"
            logger.info(f"Max emails per user: {max_emails_display}")
            logger.info(f"Include attachments: {not args.no_attachments}")
            logger.info(f"Preserve folder structure: {not args.no_folders}")
            logger.info(f"Backup format: {args.format}")
            logger.info("=" * 80)
            
            # Create configuration from command-line arguments
            config = create_config_from_args(args)
            
            # Validate configuration
            if not validate_config(config):
                logger.error("Configuration validation failed")
                sys.exit(1)
            
            # Create backup instance and run backup
            backup = ExchangeBackup(config)
            backup.backup_all()
            
            logger.info("=" * 80)
            logger.info("✅ Exchange backup completed successfully")
            logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Backup failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()