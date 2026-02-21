#!/usr/bin/env python3
"""
Optimized SharePoint Incremental Backup - FIXED VERSION
Leverages Microsoft Graph API server-side metadata (eTag, cTag, lastModifiedDateTime)
to detect file changes without downloading files unnecessarily.
"""

import os
import sys
import json
import argparse
import hashlib
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from loguru import logger
from checksum_db import BackupChecksumDB

# Configure logging
logger.remove()
logger.level("INFO", color="<green>", icon="ℹ️")
logger.level("SUCCESS", color="<bold><green>", icon="✅")
logger.level("WARNING", color="<yellow>", icon="⚠️")
logger.level("ERROR", color="<red>", icon="❌")

logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO",
    colorize=True
)


@dataclass
class FileMetadata:
    """File metadata from Graph API for change detection."""
    id: str
    name: str
    size: int
    eTag: str
    cTag: str
    lastModifiedDateTime: str
    createdDateTime: str
    webUrl: str
    file_path: str  # /drives/{driveId}/items/{itemId}
    
    @classmethod
    def from_graph_data(cls, data: Dict[str, Any], drive_id: str) -> 'FileMetadata':
        return cls(
            id=data.get('id'),
            name=data.get('name'),
            size=data.get('size', 0),
            eTag=data.get('eTag', ''),
            cTag=data.get('cTag', ''),
            lastModifiedDateTime=data.get('lastModifiedDateTime', ''),
            createdDateTime=data.get('createdDateTime', ''),
            webUrl=data.get('webUrl', ''),
            file_path=f"/drives/{drive_id}/items/{data.get('id')}"
        )


class OptimizedSharePointBackupFixed:
    """Optimized backup using server-side metadata for change detection - FIXED VERSION."""
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str, 
                 backup_dir: str = None, db_path: str = "backup_checksums.db"):
        """
        Initialize optimized backup client.
        
        Args:
            client_id: Azure AD App Client ID
            client_secret: Azure AD App Client Secret
            tenant_id: Azure AD Tenant ID
            backup_dir: Backup directory (defaults to SHAREPOINT_BACKUP_DIR or "backup")
            db_path: Path to checksum database
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        
        # Determine backup directory
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            # Try SHAREPOINT_BACKUP_DIR environment variable first
            sharepoint_backup_dir = os.environ.get('SHAREPOINT_BACKUP_DIR')
            if sharepoint_backup_dir:
                self.backup_dir = Path(sharepoint_backup_dir)
            else:
                # Fall back to BACKUP_DIR or default
                backup_dir_env = os.environ.get('BACKUP_DIR', 'backup')
                self.backup_dir = Path(backup_dir_env)
        
        self.db = BackupChecksumDB(db_path)
        
        self.access_token = self._get_access_token()
        self.token_obtained_time = datetime.now()
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        self.stats = {
            'files_backed_up': 0,
            'files_skipped': 0,
            'files_failed': 0,
            'total_size': 0,
            'bytes_saved': 0,
            'start_time': datetime.now()
        }
        
        logger.info(f"Optimized SharePoint backup initialized")
        logger.info(f"Backup directory: {self.backup_dir}")
        logger.info(f"Database: {db_path}")
    
    def _get_access_token(self) -> str:
        """Get Microsoft Graph access token."""
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        token_data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://graph.microsoft.com/.default'
        }
        
        response = requests.post(token_url, data=token_data, timeout=30)
        response.raise_for_status()
        return response.json()['access_token']
    
    def _refresh_token_if_needed(self):
        """Refresh token if needed."""
        current_time = datetime.now()
        if (current_time - self.token_obtained_time).total_seconds() > 3000:
            logger.info("Refreshing access token...")
            self.access_token = self._get_access_token()
            self.token_obtained_time = datetime.now()
            self.headers['Authorization'] = f'Bearer {self.access_token}'
    
    def _make_graph_request(self, url: str, method: str = 'GET', **kwargs):
        """Make Graph API request with token refresh."""
        self._refresh_token_if_needed()
        
        response = requests.request(method, url, headers=self.headers, **kwargs)
        
        if response.status_code == 401:
            logger.warning("Token expired, refreshing...")
            self.access_token = self._get_access_token()
            self.token_obtained_time = datetime.now()
            self.headers['Authorization'] = f'Bearer {self.access_token}'
            response = requests.request(method, url, headers=self.headers, **kwargs)
        
        return response
    
    def _has_file_changed(self, file_meta: FileMetadata) -> bool:
        """Check if file has changed using server-side metadata."""
        record = self.db.get_file_record(file_meta.file_path)
        
        if not record:
            return True  # New file
        
        # Check eTag and size for changes
        if file_meta.eTag != record.get('eTag', '') or file_meta.size != record.get('file_size', 0):
            return True
        
        return False  # Unchanged
    
    def _download_file(self, site_id: str, drive_id: str, file_meta: FileMetadata, local_path: Path) -> bool:
        """Download a file and update database."""
        try:
            download_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{file_meta.id}/content"
            response = self._make_graph_request(download_url, stream=True)
            
            if response.status_code != 200:
                logger.warning(f"Failed to download {file_meta.name}: {response.status_code}")
                return False
            
            file_path = local_path / self._sanitize_filename(file_meta.name)
            
            # Calculate checksum while downloading
            sha256_hash = hashlib.sha256()
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        sha256_hash.update(chunk)
                        f.write(chunk)
            
            checksum = sha256_hash.hexdigest()
            
            # Update database
            self.db.update_file_record(
                site_id=site_id,
                file_path=file_meta.file_path,
                file_name=file_meta.name,
                file_size=file_meta.size,
                last_modified=file_meta.lastModifiedDateTime,
                checksum=checksum,
                eTag=file_meta.eTag,
                cTag=file_meta.cTag
            )
            
            self.stats['files_backed_up'] += 1
            self.stats['total_size'] += file_meta.size
            logger.info(f"Backed up: {file_meta.name} ({file_meta.size:,} bytes)")
            
            return True
            
        except Exception as e:
            logger.warning(f"Error downloading {file_meta.name}: {str(e)}")
            self.stats['files_failed'] += 1
            return False
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename[:200]
    
    def _get_files_with_metadata(self, site_id: str, drive_id: str, folder_id: str = "root") -> List[FileMetadata]:
        """Get all files in a folder with metadata - FIXED VERSION with better error handling."""
        files = []
        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{folder_id}/children"
        
        params = {
            '$select': 'id,name,size,eTag,cTag,lastModifiedDateTime,createdDateTime,webUrl,file,parentReference',
            '$top': 200
        }
        
        try:
            page_count = 0
            total_items = 0
            while url:
                response = self._make_graph_request(url, params=params)
                if response.status_code != 200:
                    logger.warning(f"Failed to get files from {url}: {response.status_code} - {response.text[:200]}")
                    break
                
                data = response.json()
                items = data.get('value', [])
                page_count += 1
                total_items += len(items)
                
                for item in items:
                    if 'file' in item:
                        file_meta = FileMetadata.from_graph_data(item, drive_id)
                        files.append(file_meta)
                    elif 'folder' in item:
                        subfolder_id = item.get('id')
                        subfolder_files = self._get_files_with_metadata(site_id, drive_id, subfolder_id)
                        files.extend(subfolder_files)
                
                url = data.get('@odata.nextLink')
                params = {}
            
            if page_count > 0:
                logger.debug(f"Scanned {page_count} pages, {total_items} items, found {len(files)} files in folder {folder_id}")
            
            return files
            
        except Exception as e:
            logger.warning(f"Error getting files from site {site_id}, drive {drive_id}, folder {folder_id}: {str(e)}")
            return []
    
    def backup_all_sites(self, backup_type: str = 'incremental', max_workers: int = 5):
        """Main backup method."""
        logger.info(f"Starting {backup_type.upper()} SharePoint backup")
        logger.info("=" * 60)
        
        session_id = self.db.start_backup_session(backup_type)
        
        try:
            sites = self._get_all_sites()
            logger.info(f"Found {len(sites)} sites")
            
            for i, site in enumerate(sites, 1):
                site_id = site['id']
                site_name = site.get('displayName', f"Site_{i}")
                
                logger.info(f"[{i}/{len(sites)}] Processing: {site_name}")
                self._backup_site(site_id, site_name, backup_type, max_workers)
            
            self.db.update_backup_session(
                session_id=session_id,
                files_backed_up=self.stats['files_backed_up'],
                files_skipped=self.stats['files_skipped'],
                total_size=self.stats['total_size'],
                status='completed'
            )
            
            self._print_summary()
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}")
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
        """Get all SharePoint sites."""
        sites_url = "https://graph.microsoft.com/v1.0/sites?$select=id,name,webUrl,displayName"
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
    
    def _backup_site(self, site_id: str, site_name: str, backup_type: str, max_workers: int):
        """Backup a single site."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        site_path = self.backup_dir / self._sanitize_filename(site_name) / timestamp
        site_path.mkdir(parents=True, exist_ok=True)
        
        # Save site metadata
        metadata = {
            'site_id': site_id,
            'site_name': site_name,
            'backup_date': datetime.now().isoformat(),
            'backup_type': backup_type,
            'backup_directory': str(self.backup_dir)
        }
        
        with open(site_path / "site_metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Get drives
        drives = self._get_site_drives(site_id)
        logger.info(f"  Found {len(drives)} document libraries")
        
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
            
            for drive_name, future in futures:
                try:
                    future.result()
                    logger.info(f"  Completed: {drive_name}")
                except Exception as e:
                    logger.error(f"  Failed to backup drive '{drive_name}': {str(e)}")
    
    def _get_site_drives(self, site_id: str) -> List[Dict[str, Any]]:
        """Get all drives for a site."""
        drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        
        try:
            response = self._make_graph_request(drives_url)
            if response.status_code == 200:
                drives = response.json().get('value', [])
                logger.debug(f"Found {len(drives)} drives for site {site_id}")
                return drives
            else:
                logger.warning(f"Failed to get drives for site {site_id}: {response.status_code} - {response.text[:200]}")
                return []
        except Exception as e:
            logger.warning(f"Error getting drives for site {site_id}: {str(e)}")
            return []
    
    def _backup_drive(self, site_id: str, drive_id: str, drive_name: str, site_path: Path, backup_type: str):
        """Backup a document library."""
        drive_path = site_path / self._sanitize_filename(drive_name)
        drive_path.mkdir(parents=True, exist_ok=True)
        
        # Get files with metadata
        logger.info(f"    Scanning '{drive_name}'...")
        files = self._get_files_with_metadata(site_id, drive_id)
        logger.info(f"    Found {len(files)} files")
        
        # Process files
        changed_files = []
        unchanged_files = []
        
        for file_meta in files:
            if backup_type == 'full':
                changed_files.append(file_meta)
            elif self._has_file_changed(file_meta):
                changed_files.append(file_meta)
            else:
                unchanged_files.append(file_meta)
                self.stats['files_skipped'] += 1
                self.stats['bytes_saved'] += file_meta.size
        
        logger.info(f"    Changed: {len(changed_files)}, Unchanged: {len(unchanged_files)}")
        
        # Download changed files
        for file_meta in changed_files:
            self._download_file(site_id, drive_id, file_meta, drive_path)
    
    def _print_summary(self):
        """Print backup summary."""
        end_time = datetime.now()
        duration = end_time - self.stats['start_time']
        
        logger.info("=" * 60)
        logger.info("BACKUP SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Duration: {duration}")
        logger.info(f"Files backed up: {self.stats['files_backed_up']}")
        logger.info(f"Files skipped: {self.stats['files_skipped']}")
        logger.info(f"Files failed: {self.stats['files_failed']}")
        logger.info(f"Total size: {self.stats['total_size']:,} bytes")
        logger.info(f"Bytes saved: {self.stats['bytes_saved']:,} bytes")
        
        if self.stats['files_backed_up'] + self.stats['files_skipped'] > 0:
            skip_rate = (self.stats['files_skipped'] / 
                        (self.stats['files_backed_up'] + self.stats['files_skipped'])) * 100
            logger.info(f"Skip rate: {skip_rate:.1f}%")
        
        logger.info("=" * 60)


def main():
    """Command-line interface."""
    # Try to load environment variables from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("Loaded environment variables from .env file")
    except ImportError:
        logger