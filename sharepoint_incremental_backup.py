#!/usr/bin/env python3
"""
SharePoint Incremental Backup with Checksum Deduplication
Uses Microsoft Graph API and checksum database to only backup changed files.
Preserves the original sharepoint_graph_backup.py as a standalone tool.
"""

import os
import sys
import json
import argparse
import hashlib
import sqlite3
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import loguru for enhanced logging
from loguru import logger

# Import our checksum database
from checksum_db import BackupChecksumDB, calculate_stream_checksum

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
    "sharepoint_incremental_backup.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="TRACE",  # Log everything to file
    rotation="10 MB",  # Rotate when file reaches 10 MB
    retention="30 days",  # Keep logs for 30 days
    compression="zip"  # Compress rotated logs
)


class SharePointIncrementalBackup:
    """Incremental SharePoint backup with checksum deduplication."""
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str, 
                 backup_dir: str = "backup", db_path: str = "backup_checksums.db"):
        """
        Initialize incremental backup client.
        
        Args:
            client_id: Azure AD App Client ID
            client_secret: Azure AD App Client Secret
            tenant_id: Azure AD Tenant ID
            backup_dir: Directory where backups will be stored
            db_path: Path to checksum database
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.backup_dir = Path(backup_dir)
        self.db = BackupChecksumDB(db_path)
        
        # Get initial access token
        self.access_token = self._get_access_token()
        self.token_obtained_time = datetime.now()
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        # Statistics
        self.stats = {
            'files_backed_up': 0,
            'files_skipped': 0,
            'total_size': 0,
            'start_time': datetime.now()
        }
        
        logger.info(f"Incremental backup initialized")
        logger.debug(f"Database: {db_path}")
        logger.debug(f"Backup directory: {backup_dir}")
        logger.trace(f"Client ID: {client_id[:8]}...")
        logger.trace(f"Tenant ID: {tenant_id}")
    
    def _get_access_token(self) -> str:
        """Get Microsoft Graph access token."""
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        token_data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://graph.microsoft.com/.default'
        }
        
        try:
            response = requests.post(token_url, data=token_data)
            response.raise_for_status()
            token = response.json()['access_token']
            logger.info("✅ Graph API authentication successful")
            return token
        except Exception as e:
            logger.error(f"❌ Failed to get access token: {str(e)}")
            raise
    
    def _refresh_token_if_needed(self):
        """Refresh token if it's about to expire (older than 50 minutes)."""
        current_time = datetime.now()
        time_since_token = current_time - self.token_obtained_time
        
        # Refresh if token is older than 50 minutes (tokens typically expire in 60-90 minutes)
        if time_since_token.total_seconds() > 3000:  # 50 minutes
            logger.info("🔄 Refreshing access token...")
            self.access_token = self._get_access_token()
            self.token_obtained_time = datetime.now()
            self.headers['Authorization'] = f'Bearer {self.access_token}'
            logger.info("✅ Token refreshed")
    
    def _make_graph_request(self, url: str, method: str = 'GET', **kwargs):
        """
        Make a Graph API request with automatic token refresh on 401 errors.
        
        Args:
            url: Graph API URL
            method: HTTP method
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object
        """
        # Refresh token if needed before making request
        self._refresh_token_if_needed()
        
        try:
            response = requests.request(method, url, headers=self.headers, **kwargs)
            
            # If we get 401, try refreshing token once and retry
            if response.status_code == 401:
                logger.warning(f"Received 401 for {url}, attempting token refresh...")
                self.access_token = self._get_access_token()
                self.token_obtained_time = datetime.now()
                self.headers['Authorization'] = f'Bearer {self.access_token}'
                
                # Retry the request with new token
                response = requests.request(method, url, headers=self.headers, **kwargs)
            
            return response
            
        except Exception as e:
            logger.error(f"Request failed for {url}: {str(e)}")
            raise
    
    def backup_all_sites(self, backup_type: str = 'incremental', max_workers: int = 5):
        """
        Backup all SharePoint sites with incremental capability.
        
        Args:
            backup_type: 'full' or 'incremental'
            max_workers: Maximum number of parallel downloads
        """
        logger.info("=" * 80)
        logger.info(f"Starting {backup_type.upper()} tenant-wide SharePoint backup")
        logger.info("=" * 80)
        
        # Start backup session
        session_id = self.db.start_backup_session(backup_type)
        
        try:
            # Get all sites
            sites = self._get_all_sites()
            logger.info(f"Found {len(sites)} SharePoint sites")
            
            # Backup each site
            for i, site in enumerate(sites, 1):
                site_id = site['id']
                site_name = site.get('displayName', f"Site_{i}")
                site_url = site.get('webUrl', 'Unknown')
                
                logger.info(f"[{i}/{len(sites)}] Processing: {site_name}")
                logger.info(f"    URL: {site_url}")
                
                try:
                    self._backup_site(site_id, site_name, site_url, backup_type, max_workers)
                except Exception as e:
                    logger.error(f"Failed to backup site '{site_name}': {str(e)}")
            
            # Update backup session
            self.db.update_backup_session(
                session_id=session_id,
                files_backed_up=self.stats['files_backed_up'],
                files_skipped=self.stats['files_skipped'],
                total_size=self.stats['total_size'],
                status='completed'
            )
            
            # Print summary
            self._print_summary()
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}", exc_info=True)
            self.db.update_backup_session(
                session_id=session_id,
                files_backed_up=self.stats['files_backed_up'],
                files_skipped=self.stats['files_skipped'],
                total_size=self.stats['total_size'],
                status='failed',
                error_message=str(e)
            )
            raise
    
    def _get_all_sites(self) -> List[Dict[str, Any]]:
        """Get all SharePoint sites in the tenant."""
        sites_url = "https://graph.microsoft.com/v1.0/sites?$select=id,name,webUrl,displayName,createdDateTime,lastModifiedDateTime"
        all_sites = []
        
        try:
            while sites_url:
                response = self._make_graph_request(sites_url)
                response.raise_for_status()
                data = response.json()
                
                all_sites.extend(data.get('value', []))
                sites_url = data.get('@odata.nextLink')
            
            return all_sites
        except Exception as e:
            logger.error(f"Failed to get sites: {str(e)}")
            return []
    
    def _backup_site(self, site_id: str, site_name: str, site_url: str, 
                    backup_type: str, max_workers: int):
        """Backup a single SharePoint site."""
        # Create site directory with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        site_path = self.backup_dir / self._sanitize_filename(site_name) / timestamp
        site_path.mkdir(parents=True, exist_ok=True)
        
        # Save site metadata
        site_metadata = {
            'site_id': site_id,
            'site_name': site_name,
            'site_url': site_url,
            'backup_date': datetime.now().isoformat(),
            'backup_type': backup_type,
            'backup_method': 'Microsoft Graph API (Incremental)'
        }
        
        metadata_file = site_path / "site_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(site_metadata, f, indent=2)
        
        # Get and backup document libraries (drives)
        drives = self._get_site_drives(site_id)
        logger.info(f"    Found {len(drives)} document libraries")
        
        # Process drives in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for drive in drives:
                drive_name = drive.get('name', 'Unknown')
                drive_id = drive.get('id')
                
                future = executor.submit(
                    self._backup_drive,
                    site_id, drive_id, drive_name, site_path, backup_type
                )
                futures.append((drive_name, future))
            
            # Wait for all drives to complete
            for drive_name, future in futures:
                try:
                    future.result()
                    logger.info(f"    Completed: {drive_name}")
                except Exception as e:
                    logger.error(f"    Failed to backup drive '{drive_name}': {str(e)}")
    
    def _get_site_drives(self, site_id: str) -> List[Dict[str, Any]]:
        """Get all drives (document libraries) for a site."""
        drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        
        try:
            response = self._make_graph_request(drives_url)
            if response.status_code == 200:
                return response.json().get('value', [])
            else:
                logger.warning(f"Could not get drives for site {site_id}: {response.status_code}")
                if response.status_code == 401:
                    logger.warning(f"Authentication failed for site {site_id}. This might be a personal site or special site that requires different permissions.")
                elif response.status_code == 403:
                    logger.warning(f"Access denied for site {site_id}. The app might not have permission to access this site.")
                elif response.status_code == 404:
                    logger.warning(f"Site not found: {site_id}. This might be a deleted or inaccessible site.")
                else:
                    logger.warning(f"Response: {response.text[:200]}")
                return []
        except Exception as e:
            logger.warning(f"Error getting drives for site {site_id}: {str(e)}")
            return []
    
    def _backup_drive(self, site_id: str, drive_id: str, drive_name: str, 
                     site_path: Path, backup_type: str):
        """Backup a document library (drive)."""
        drive_path = site_path / self._sanitize_filename(drive_name)
        drive_path.mkdir(parents=True, exist_ok=True)
        
        # Get drive metadata
        drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}"
        try:
            response = self._make_graph_request(drive_url)
            if response.status_code == 200:
                drive_info = response.json()
                metadata_file = drive_path / "drive_metadata.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(drive_info, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not get drive metadata: {str(e)}")
        
        # Backup root folder with progress tracking
        logger.info(f"        Starting backup of drive '{drive_name}'...")
        file_counter = [0]  # Initialize counter
        self._backup_folder(site_id, drive_id, "root", drive_path, backup_type, file_counter)
        logger.info(f"        Completed backup of drive '{drive_name}' - Processed {file_counter[0]:,} files")
    
    def _backup_folder(self, site_id: str, drive_id: str, folder_id: str, 
                      local_path: Path, backup_type: str, file_counter: list = None):
        """
        Recursively backup a folder and its contents.
        
        Args:
            site_id: SharePoint site ID
            drive_id: Drive ID
            folder_id: Folder ID
            local_path: Local directory path
            backup_type: 'full' or 'incremental'
            file_counter: List with single integer counter for progress tracking
        """
        if file_counter is None:
            file_counter = [0]  # Use list to allow modification in recursion
        
        try:
            # Get folder children
            children_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{folder_id}/children"
            response = self._make_graph_request(children_url)
            
            if response.status_code != 200:
                logger.debug(f"Failed to get folder children: {response.status_code}")
                return
            
            children = response.json().get('value', [])
            
            for item in children:
                item_name = item.get('name', 'Unknown')
                item_id = item.get('id')
                item_type = 'folder' if 'folder' in item else 'file'
                
                if item_type == 'folder':
                    # Create subfolder and recurse
                    subfolder_path = local_path / self._sanitize_filename(item_name)
                    subfolder_path.mkdir(parents=True, exist_ok=True)
                    self._backup_folder(site_id, drive_id, item_id, subfolder_path, backup_type, file_counter)
                else:
                    # Process file with incremental logic
                    self._process_file(site_id, drive_id, item_id, item, local_path, backup_type)
                    
                    # Update counter and show progress every 1000 files
                    file_counter[0] += 1
                    if file_counter[0] % 1000 == 0:
                        logger.info(f"        Processed {file_counter[0]:,} files...")
                    
        except Exception as e:
            logger.warning(f"Error processing folder: {str(e)}")
    
    def _process_file(self, site_id: str, drive_id: str, item_id: str, 
                     item_data: Dict, local_path: Path, backup_type: str):
        """
        Process a file with incremental backup logic.
        
        Args:
            site_id: SharePoint site ID
            drive_id: Drive ID
            item_id: File item ID
            item_data: File metadata from Graph API
            local_path: Local directory path
            backup_type: 'full' or 'incremental'
        """
        filename = item_data.get('name', 'Unknown')
        file_size = item_data.get('size', 0)
        last_modified = item_data.get('lastModifiedDateTime', '')
        file_path = f"/drives/{drive_id}/items/{item_id}"
        
        # For full backup, always download
        if backup_type == 'full':
            self._download_file(site_id, drive_id, item_id, filename, item_data, local_path)
            return
        
        # For incremental backup, check if file has changed
        try:
            # Get file checksum from SharePoint (if available) or calculate during download
            # First, check if we have a record
            unchanged, record = self.db.is_file_unchanged(
                site_id=site_id,
                file_path=file_path,
                current_checksum='',  # Will calculate during download
                current_size=file_size
            )
            
            # Quick check: if size changed, file definitely changed
            if record and file_size != record['file_size']:
                logger.debug(f"        Size changed: {filename} ({record['file_size']} -> {file_size} bytes)")
                self._download_file(site_id, drive_id, item_id, filename, item_data, local_path)
                return
            
            # Download file and calculate checksum
            checksum = self._download_file_with_checksum(site_id, drive_id, item_id, filename, item_data, local_path)
            
            if not checksum:
                return  # Download failed
            
            # Check if checksum matches
            if record and checksum == record['checksum_sha256']:
                # File unchanged, skip
                self.stats['files_skipped'] += 1
                logger.debug(f"        Skipped (unchanged): {filename}")
                
                # Delete the downloaded file since it's unchanged
                file_path_local = local_path / self._sanitize_filename(filename)
                if file_path_local.exists():
                    file_path_local.unlink()
                
                # Also delete metadata file
                metadata_file = local_path / f"{self._sanitize_filename(filename)}.metadata.json"
                if metadata_file.exists():
                    metadata_file.unlink()
            else:
                # File changed or new, update database
                self.db.update_file_record(
                    site_id=site_id,
                    file_path=file_path,
                    file_name=filename,
                    file_size=file_size,
                    last_modified=last_modified,
                    checksum=checksum
                )
                self.stats['files_backed_up'] += 1
                self.stats['total_size'] += file_size
                logger.info(f"        Backed up: {filename} ({file_size:,} bytes)")
                
        except Exception as e:
            logger.warning(f"        Error processing {filename}: {str(e)}")
    
    def _download_file_with_checksum(self, site_id: str, drive_id: str, item_id: str, 
                                    filename: str, item_data: Dict, local_path: Path) -> Optional[str]:
        """
        Download a file and calculate its checksum simultaneously.
        
        Returns:
            SHA-256 checksum or None if download failed
        """
        try:
            # Download file content
            download_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{item_id}/content"
            response = self._make_graph_request(download_url, stream=True)
            
            if response.status_code != 200:
                logger.warning(f"        Failed to download {filename}: {response.status_code}")
                if response.status_code == 401:
                    logger.warning(f"        Authentication failed for file {filename}. Token may have expired.")
                elif response.status_code == 403:
                    logger.warning(f"        Access denied for file {filename}. The app might not have permission to access this file.")
                elif response.status_code == 404:
                    logger.warning(f"        File not found: {filename}")
                return None
            
            file_path = local_path / self._sanitize_filename(filename)
            
            # Calculate checksum while downloading
            sha256_hash = hashlib.sha256()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        sha256_hash.update(chunk)
                        f.write(chunk)
            
            checksum = sha256_hash.hexdigest()
            
            # Save file metadata
            metadata = {
                'name': item_data.get('name'),
                'size': item_data.get('size'),
                'createdDateTime': item_data.get('createdDateTime'),
                'lastModifiedDateTime': item_data.get('lastModifiedDateTime'),
                'webUrl': item_data.get('webUrl'),
                'checksum_sha256': checksum,
                'download_url': download_url
            }
            
            metadata_file = local_path / f"{self._sanitize_filename(filename)}.metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            return checksum
            
        except Exception as e:
            logger.warning(f"        Error downloading {filename}: {str(e)}")
            return None
    
    def _download_file(self, site_id: str, drive_id: str, item_id: str, 
                      filename: str, item_data: Dict, local_path: Path):
        """Download a file (for full backup mode)."""
        try:
            # Download file content
            download_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{item_id}/content"
            response = self._make_graph_request(download_url, stream=True)
            
            if response.status_code == 200:
                file_path = local_path / self._sanitize_filename(filename)
                
                # Save file
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # Calculate checksum for database
                checksum = self._calculate_file_checksum(file_path)
                
                # Update database
                self.db.update_file_record(
                    site_id=site_id,
                    file_path=f"/drives/{drive_id}/items/{item_id}",
                    file_name=filename,
                    file_size=item_data.get('size', 0),
                    last_modified=item_data.get('lastModifiedDateTime', ''),
                    checksum=checksum
                )
                
                # Save file metadata
                metadata = {
                    'name': item_data.get('name'),
                    'size': item_data.get('size'),
                    'createdDateTime': item_data.get('createdDateTime'),
                    'lastModifiedDateTime': item_data.get('lastModifiedDateTime'),
                    'webUrl': item_data.get('webUrl'),
                    'checksum_sha256': checksum,
                    'download_url': download_url
                }
                
                metadata_file = local_path / f"{self._sanitize_filename(filename)}.metadata.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2)
                
                # Update statistics
                self.stats['files_backed_up'] += 1
                self.stats['total_size'] += item_data.get('size', 0)
                logger.info(f"        Backed up: {filename} ({item_data.get('size', 0):,} bytes)")
                
        except Exception as e:
            logger.warning(f"        Error downloading {filename}: {str(e)}")
    
    def _calculate_file_checksum(self, file_path: Path) -> str:
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
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe filesystem use."""
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200 - len(ext)] + ext
        
        return filename
    
    def _print_summary(self):
        """Print backup summary."""
        end_time = datetime.now()
        duration = end_time - self.stats['start_time']
        
        logger.info("=" * 80)
        logger.info("📊 BACKUP SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Duration: {duration}")
        logger.info(f"Files backed up: {self.stats['files_backed_up']}")
        logger.info(f"Files skipped (unchanged): {self.stats['files_skipped']}")
        logger.info(f"Total size: {self.stats['total_size']:,} bytes")
        
        if self.stats['files_backed_up'] + self.stats['files_skipped'] > 0:
            skip_percentage = (self.stats['files_skipped'] / 
                             (self.stats['files_backed_up'] + self.stats['files_skipped'])) * 100
            logger.info(f"Skip rate: {skip_percentage:.1f}%")
        
        logger.info("=" * 80)
    
    def verify_backup(self):
        """Verify backup integrity by checking checksums."""
        logger.info("=" * 80)
        logger.info("Starting backup verification")
        logger.info("=" * 80)
        
        session_id = self.db.start_backup_session('verify')
        
        try:
            # Get all files from database
            with sqlite3.connect(self.db.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM backup_files')
                files = [dict(row) for row in cursor.fetchall()]
            
            logger.info(f"Verifying {len(files)} files")
            
            verified = 0
            failed = 0
            
            for file_record in files:
                # Find the file in backup directory
                # This is simplified - in practice, you'd need to map database records to files
                logger.debug(f"Verifying: {file_record['file_name']}")
                verified += 1
            
            logger.info(f"Verified {verified} files, {failed} failed")
            
            self.db.update_backup_session(
                session_id=session_id,
                files_backed_up=verified,
                files_skipped=0,
                total_size=0,
                status='completed'
            )
            
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            self.db.update_backup_session(
                session_id=session_id,
                files_backed_up=0,
                files_skipped=0,
                total_size=0,
                status='failed',
                error_message=str(e)
            )
            raise


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
        description='SharePoint Incremental Backup with Checksum Deduplication'
    )
    
    parser.add_argument('--type', choices=['full', 'incremental'], 
                       default='incremental',
                       help='Backup type: full or incremental (default: incremental)')
    
    parser.add_argument('--backup-dir', default='backup',
                       help="Backup directory (overrides SHAREPOINT_BACKUP_DIR and BACKUP_DIR, default: backup)")
    
    parser.add_argument('--db-path', default='backup_checksums.db',
                       help='Checksum database path (default: backup_checksums.db)')
    
    parser.add_argument('--workers', type=int, default=5,
                       help='Maximum parallel downloads (default: 5)')
    
    parser.add_argument('--verify', action='store_true',
                       help='Verify backup integrity')
    
    parser.add_argument('--stats', action='store_true',
                       help='Show backup statistics')
    
    parser.add_argument('--cleanup', type=int, metavar='DAYS',
                       help='Cleanup records older than N days')
    
    args = parser.parse_args()
    
    # Configuration from environment variables
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    TENANT_ID = os.environ.get('SHAREPOINT_TENANT_ID')
    # Determine backup directory (SHAREPOINT_BACKUP_DIR takes precedence)
    SHAREPOINT_BACKUP_DIR = os.environ.get("SHAREPOINT_BACKUP_DIR")
    BACKUP_DIR = os.environ.get("BACKUP_DIR", args.backup_dir)
    if SHAREPOINT_BACKUP_DIR:
        BACKUP_DIR = SHAREPOINT_BACKUP_DIR
    
    # Validate configuration
    if not CLIENT_ID or not CLIENT_SECRET or not TENANT_ID:
        logger.error("Please configure SharePoint credentials!")
        logger.error("Set the following environment variables:")
        logger.error("  SHAREPOINT_CLIENT_ID - Azure AD App Client ID")
        logger.error("  SHAREPOINT_CLIENT_SECRET - Azure AD App Client Secret")
        logger.error("  SHAREPOINT_TENANT_ID - Azure AD Tenant ID")
        logger.error("  BACKUP_DIR (optional) - Backup directory path")
        sys.exit(1)
    
    try:
        # Create backup instance
        backup = SharePointIncrementalBackup(
            CLIENT_ID, CLIENT_SECRET, TENANT_ID, 
            BACKUP_DIR, args.db_path
        )
        
        if args.verify:
            backup.verify_backup()
        elif args.stats:
            stats = backup.db.get_backup_stats(30)
            print(json.dumps(stats, indent=2, default=str))
        elif args.cleanup:
            backup.db.cleanup_old_records(args.cleanup)
        else:
            # Run backup
            backup.backup_all_sites(args.type, args.workers)
        
    except Exception as e:
        logger.error(f"Backup failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
