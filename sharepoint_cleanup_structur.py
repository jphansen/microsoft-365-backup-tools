#!/usr/bin/env python3
"""
SharePoint Backup Cleanup Script

This script consolidates multiple timestamped backup directories into a single
consolidated timestamp directory (format: consolidated_YYYYMMDD_HHMMSS), 
keeping only the newest versions of files.

Usage:
    python3 sharepoint_cleanup_structur.py [--root-dir ROOT_DIR] [--dry-run] [--verbose]

Example:
    python3 sharepoint_cleanup_structur.py --root-dir BACKUP/sundbusserne/sharepoint --dry-run
"""

import os
import sys
import argparse
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Tuple
import re

# Configure logging
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SharePointBackupCleanup:
    """Cleanup and consolidate SharePoint backup directories."""
    
    # Regex pattern to match timestamp directories (YYYYMMDD_HHMMSS)
    TIMESTAMP_PATTERN = re.compile(r'^\d{8}_\d{6}$')
    
    def __init__(self, root_dir: Path, dry_run: bool = False, verbose: bool = False):
        """
        Initialize the cleanup utility.
        
        Args:
            root_dir: Root directory containing SharePoint backup structure
            dry_run: If True, only show what would be done without making changes
            verbose: If True, show detailed progress information
        """
        self.root_dir = Path(root_dir).resolve()
        self.dry_run = dry_run
        self.verbose = verbose
        
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        # Statistics
        self.stats = {
            'sites_processed': 0,
            'timestamp_dirs_found': 0,
            'files_copied': 0,
            'files_skipped': 0,
            'directories_created': 0,
            'old_dirs_removed': 0,
            'errors': 0
        }
        
        logger.info(f"Initialized SharePoint backup cleanup")
        logger.info(f"Root directory: {self.root_dir}")
        logger.info(f"Dry run: {dry_run}")
        logger.info(f"Verbose: {verbose}")
    
    def is_timestamp_directory(self, dir_name: str) -> bool:
        """Check if a directory name matches the timestamp pattern."""
        return bool(self.TIMESTAMP_PATTERN.match(dir_name))
    
    def parse_timestamp(self, dir_name: str) -> datetime:
        """Parse timestamp from directory name."""
        try:
            return datetime.strptime(dir_name, '%Y%m%d_%H%M%S')
        except ValueError:
            # If parsing fails, return a very old date
            return datetime(1970, 1, 1)
    
    def find_site_directories(self) -> List[Path]:
        """Find all site directories that contain timestamped subdirectories."""
        site_dirs = []
        
        logger.info(f"Scanning for site directories in {self.root_dir}...")
        
        # First check if the root directory itself contains timestamp directories
        has_timestamp_dirs_in_root = False
        try:
            for item in self.root_dir.iterdir():
                if item.is_dir() and self.is_timestamp_directory(item.name):
                    has_timestamp_dirs_in_root = True
                    break
        except (PermissionError, OSError) as e:
            logger.warning(f"Could not access {self.root_dir}: {e}")
        
        # If root contains timestamp directories, treat it as a site directory
        if has_timestamp_dirs_in_root:
            site_dirs.append(self.root_dir)
            if self.verbose:
                logger.debug(f"Root directory contains timestamp directories: {self.root_dir.name}")
        
        # Also check for nested site directories
        for item in self.root_dir.iterdir():
            if item.is_dir() and item != self.root_dir:  # Skip if we already added root
                # Check if this directory contains timestamped subdirectories
                has_timestamp_dirs = False
                try:
                    for subitem in item.iterdir():
                        if subitem.is_dir() and self.is_timestamp_directory(subitem.name):
                            has_timestamp_dirs = True
                            break
                except (PermissionError, OSError) as e:
                    logger.warning(f"Could not access {item}: {e}")
                    continue
                
                if has_timestamp_dirs:
                    site_dirs.append(item)
                    if self.verbose:
                        logger.debug(f"Found site directory: {item.name}")
        
        logger.info(f"Found {len(site_dirs)} site directories with timestamped backups")
        return site_dirs
    
    def get_timestamp_directories(self, site_dir: Path) -> List[Tuple[datetime, Path]]:
        """Get all timestamp directories for a site, sorted by timestamp (newest first)."""
        timestamp_dirs = []
        
        for item in site_dir.iterdir():
            if item.is_dir() and self.is_timestamp_directory(item.name):
                timestamp = self.parse_timestamp(item.name)
                timestamp_dirs.append((timestamp, item))
        
        # Sort by timestamp, newest first
        timestamp_dirs.sort(key=lambda x: x[0], reverse=True)
        
        return timestamp_dirs
    
    def should_process_file(self, src_file: Path, dst_file: Path) -> bool:
        """
        Determine if a file should be copied.
        
        Returns True if:
        - Destination file doesn't exist, OR
        - Source file is newer than destination file
        """
        if not dst_file.exists():
            return True
        
        try:
            src_mtime = src_file.stat().st_mtime
            dst_mtime = dst_file.stat().st_mtime
            return src_mtime > dst_mtime
        except (OSError, FileNotFoundError) as e:
            logger.warning(f"Could not compare file timestamps: {e}")
            return True  # Copy if we can't determine
    
    def copy_file(self, src_file: Path, dst_file: Path) -> bool:
        """Copy a file with proper error handling."""
        try:
            # Create parent directories if they don't exist
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            
            if self.dry_run:
                logger.debug(f"Would copy: {src_file} -> {dst_file}")
                self.stats['files_copied'] += 1
                return True
            
            # Copy the file
            shutil.copy2(src_file, dst_file)
            logger.debug(f"Copied: {src_file} -> {dst_file}")
            self.stats['files_copied'] += 1
            self.stats['directories_created'] += 1 if not dst_file.parent.exists() else 0
            return True
            
        except (OSError, IOError, shutil.Error) as e:
            logger.error(f"Failed to copy {src_file} to {dst_file}: {e}")
            self.stats['errors'] += 1
            return False
    
    def process_site_directory(self, site_dir: Path):
        """Process a single site directory, consolidating timestamped backups."""
        site_name = site_dir.name
        logger.info(f"Processing site: {site_name}")
        
        # Get all timestamp directories, sorted newest first
        timestamp_dirs = self.get_timestamp_directories(site_dir)
        
        if not timestamp_dirs:
            logger.warning(f"No timestamp directories found in {site_dir}")
            return
        
        self.stats['timestamp_dirs_found'] += len(timestamp_dirs)
        
        # Determine target directory name
        # Use a consolidated timestamp directory name instead of "master"
        # Format: consolidated_YYYYMMDD_HHMMSS (using current time)
        from datetime import datetime
        consolidated_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir_name = f"consolidated_{consolidated_timestamp}"
        target_dir = site_dir / target_dir_name
        
        logger.info(f"  Found {len(timestamp_dirs)} timestamp directories")
        logger.info(f"  Consolidating into: {target_dir}")
        
        if self.dry_run:
            logger.info(f"  Dry run: Would create {target_dir} and copy newest files")
        else:
            # Create target directory if it doesn't exist
            target_dir.mkdir(exist_ok=True)
        
        # Track which files we've already copied (to avoid overwriting with older versions)
        copied_files: Set[Path] = set()
        
        # Process directories from newest to oldest
        for timestamp, timestamp_dir in timestamp_dirs:
            logger.info(f"  Processing backup from {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Walk through all files in this timestamp directory
            for root, dirs, files in os.walk(timestamp_dir):
                root_path = Path(root)
                
                for file_name in files:
                    src_file = root_path / file_name
                    
                    # Calculate relative path from timestamp directory
                    rel_path = src_file.relative_to(timestamp_dir)
                    
                    # Calculate destination path in target directory
                    dst_file = target_dir / rel_path
                    
                    # Skip if we've already copied a newer version of this file
                    if dst_file in copied_files:
                        if self.verbose:
                            logger.debug(f"    Skipping (already copied newer version): {rel_path}")
                        self.stats['files_skipped'] += 1
                        continue
                    
                    # Check if we should copy this file
                    if self.should_process_file(src_file, dst_file):
                        if self.copy_file(src_file, dst_file):
                            copied_files.add(dst_file)
                    else:
                        if self.verbose:
                            logger.debug(f"    Skipping (older version): {rel_path}")
                        self.stats['files_skipped'] += 1
        
        # After consolidating files, we could optionally remove old timestamp directories
        # For safety, we'll leave them in place unless explicitly requested
        
        self.stats['sites_processed'] += 1
        logger.info(f"  Completed processing {site_name}")
    
    def cleanup_old_directories(self, site_dir: Path, keep_newest: int = 1):
        """
        Remove old timestamp directories after consolidation.
        
        Args:
            site_dir: Site directory to clean up
            keep_newest: Number of newest timestamp directories to keep (default: 1)
        """
        if self.dry_run:
            logger.info(f"  Dry run: Would remove old timestamp directories (keeping {keep_newest} newest)")
            return
        
        # Get all timestamp directories, sorted newest first
        timestamp_dirs = self.get_timestamp_directories(site_dir)
        
        if len(timestamp_dirs) <= keep_newest:
            logger.info(f"  Not enough directories to clean up (keeping all {len(timestamp_dirs)})")
            return
        
        # Keep the newest directories
        to_keep = timestamp_dirs[:keep_newest]
        to_remove = timestamp_dirs[keep_newest:]
        
        for timestamp, dir_path in to_remove:
            try:
                logger.info(f"  Removing old directory: {dir_path.name}")
                shutil.rmtree(dir_path)
                self.stats['old_dirs_removed'] += 1
            except (OSError, shutil.Error) as e:
                logger.error(f"  Failed to remove {dir_path}: {e}")
                self.stats['errors'] += 1
    
    def run(self, cleanup_old: bool = False, keep_newest: int = 1):
        """Run the cleanup process."""
        logger.info("=" * 60)
        logger.info("Starting SharePoint backup cleanup")
        logger.info("=" * 60)
        
        try:
            # Find all site directories
            site_dirs = self.find_site_directories()
            
            if not site_dirs:
                logger.warning("No site directories found. Nothing to do.")
                return
            
            # Process each site directory
            for site_dir in site_dirs:
                try:
                    self.process_site_directory(site_dir)
                    
                    # Optionally clean up old directories
                    if cleanup_old:
                        self.cleanup_old_directories(site_dir, keep_newest)
                        
                except Exception as e:
                    logger.error(f"Error processing site directory {site_dir}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Print summary
            self.print_summary()
            
        except Exception as e:
            logger.error(f"Fatal error during cleanup: {e}")
            self.stats['errors'] += 1
            raise
    
    def print_summary(self):
        """Print cleanup summary."""
        logger.info("=" * 60)
        logger.info("CLEANUP SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Sites processed: {self.stats['sites_processed']}")
        logger.info(f"Timestamp directories found: {self.stats['timestamp_dirs_found']}")
        logger.info(f"Files copied: {self.stats['files_copied']}")
        logger.info(f"Files skipped: {self.stats['files_skipped']}")
        logger.info(f"Directories created: {self.stats['directories_created']}")
        logger.info(f"Old directories removed: {self.stats['old_dirs_removed']}")
        logger.info(f"Errors: {self.stats['errors']}")
        
        if self.dry_run:
            logger.info("NOTE: This was a dry run. No changes were made.")
        
        logger.info("=" * 60)


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description='Consolidate SharePoint backup directories into consolidated timestamp directories'
    )
    
    parser.add_argument('--root-dir', default='BACKUP',
                       help='Root directory containing SharePoint backup structure '
                            '(default: BACKUP)')
    
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose output')
    
    parser.add_argument('--cleanup-old', action='store_true',
                       help='Remove old timestamp directories after consolidation')
    
    parser.add_argument('--keep-newest', type=int, default=1,
                       help='Number of newest timestamp directories to keep when '
                            'cleaning up (default: 1)')
    
    args = parser.parse_args()
    
    # Validate arguments
    root_dir = Path(args.root_dir)
    if not root_dir.exists():
        logger.error(f"Root directory does not exist: {root_dir}")
        sys.exit(1)
    
    if not root_dir.is_dir():
        logger.error(f"Root directory is not a directory: {root_dir}")
        sys.exit(1)
    
    if args.keep_newest < 0:
        logger.error("keep-newest must be 0 or greater")
        sys.exit(1)
    
    try:
        # Run the cleanup
        cleanup = SharePointBackupCleanup(
            root_dir=root_dir,
            dry_run=args.dry_run,
            verbose=args.verbose
        )
        
        cleanup.run(
            cleanup_old=args.cleanup_old,
            keep_newest=args.keep_newest
        )
        
    except KeyboardInterrupt:
        logger.info("Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()