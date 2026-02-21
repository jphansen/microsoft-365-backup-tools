#!/usr/bin/env python3
"""
Optimized SharePoint Incremental Backup with Server-Side Metadata
Complete implementation using eTag, cTag, and lastModifiedDateTime for change detection.
"""

import os
import sys
import json
import argparse
import hashlib
import sqlite3
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import time

# Import loguru for enhanced logging
from loguru import logger

# Import our checksum database
from checksum_db import BackupChecksumDB

# Configure loguru
logger.remove()
logger.level("TRACE", color="<cyan>", icon="🔍")
logger.level("DEBUG", color="<blue>", icon="🐛")
logger.level("INFO", color="<green>", icon="ℹ️")
logger.level("SUCCESS", color="<bold><green>", icon="✅")
logger.level("WARNING", color="<yellow>", icon="⚠️")
logger.level("ERROR", color="<red>", icon="❌")
logger.level("CRITICAL", color="<bold><red>", icon="💥")

logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
    colorize=True
)

logger.add(
    "sharepoint_incremental_backup_optimized.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="TRACE",
    rotation="10 MB",
    retention="30 days",
    compression="zip"
)


@dataclass
class FileMetadata:
    """Container for file metadata from Graph API."""
    id: str
    name: str
    size: int
    eTag: str
    cTag: str
    lastModifiedDateTime: str
    createdDateTime: str
    webUrl: str
    file_path: str  # Graph API path like /drives/{driveId}/items/{itemId}
    mimeType: str = ""
    parentReference: Dict = None
    
    @classmethod
    def from_graph_data(cls, data: Dict[str, Any], drive_id: str) -> 'FileMetadata':
        """Create FileMetadata from Graph API response."""
        return cls(
            id=data.get('id'),
            name=data.get('name'),
            size=data.get('size', 0),
            eTag=data.get('eTag', ''),
            cTag=data.get('cTag', ''),
            lastModifiedDateTime=data.get('lastModifiedDateTime', ''),
            createdDateTime=data.get('createdDateTime', ''),
            webUrl=data.get('webUrl', ''),
            file_path=f"/drives/{drive_id}/items/{data.get('id')}",
            mimeType=data.get('file', {}).get('mimeType', ''),
            parentReference=data.get('parentReference', {})
        )
    
    def get_change_key(self) -> str:
        """Get a unique key for detecting changes (eTag + size)."""
        return f"{self.eTag}:{self.size}"


class OptimizedSharePointBackup:
    """Optimized SharePoint backup using server-side metadata for change detection."""
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str, 
                 backup_dir: str = "backup", db_path: str = "backup_checksums.db"):
        """
        Initialize optimized backup client.
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
            'files_failed': 0,
            'total_size': 0,
            'api_calls': 0,
            'bytes_saved': 0,
            'start_time': datetime.now()
        }
        
        logger.info(f"Optimized incremental backup initialized")
    
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
            response = requests.post(token_url, data=token_data, timeout=30)
            response.raise_for_status()
            token = response.json()['access_token']
            logger.info("✅ Graph API authentication successful")
            return token
        except Exception as e:
            logger.error(f"❌ Failed to get access token: {str(e)}")
            raise
    
    def _refresh_token_if_needed(self):
        """Refresh token if it's about to expire."""
        current_time = datetime.now()
        time_since_token = current_time - self.token_obtained_time
        
        if time_since_token.total_seconds() > 3000:  # 50 minutes
            logger.info("🔄 Refreshing access token...")
            self.access_token = self._get_access_token()
            self.token_obtained_time = datetime.now()
            self.headers['Authorization'] = f'Bearer {self.access_token}'
            logger.info("✅ Token refreshed")
    
    def _make_graph_request(self, url: str, method: str = 'GET', **kwargs):
        """Make a Graph API request with automatic token refresh."""
        self._refresh_token_if_needed()
        self.stats['api_calls'] += 1
        
        try:
            response = requests.request(method, url, headers=self.headers, **kwargs)
            
            if response.status_code == 401:
                logger.warning(f"Received 401 for {url}, attempting token refresh...")
                self.access_token = self._get_access_token()
                self.token_obtained_time = datetime.now()
                self.headers['Authorization'] = f'Bearer {self.access_token}'
                response = requests.request(method, url, headers=self.headers, **kwargs)
            
            return response
            
        except Exception as e:
            logger.error(f"Request failed for {url}: {str(e)}")
            raise
    
    def _has_file_changed(self, file_meta: FileMetadata) -> bool:
        """
        Check if file has changed using server-side metadata.
        Returns True if file needs to be downloaded, False if unchanged.
        """
        # Get existing record from database
        record = self.db.get_file_record(file_meta.file_path)
        
        if not record:
            # New file, needs backup
            return True
        
        # Check if eTag or size changed
        if file_meta.eTag != record.get('eTag', '') or file_meta.size != record.get('file_size', 0):
            return True
        
        # File unchanged
        return False
    
    def _download_file_with_checksum(self, site_id: str, drive_id: str, 
                                    file_meta: FileMetadata, local_path: Path) -> Optional[str]:
        """Download a file and calculate its checksum."""
        try:
            download_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{file_meta.id}/content"
            response = self._make_graph_request(download_url, stream=True)
            
            if response.status_code != 200:
                logger.warning(f"Failed to download {file_meta.name}: {response.status_code}")
                return None
            
            file_path = local_path / self._sanitize_filename(file_meta.name)
            
            # Calculate checksum while downloading
            sha256_hash = hashlib.sha256()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        sha256_hash.update(chunk)
                        f.write(chunk)
            
            checksum = sha256_hash.hexdigest()
            
            # Save metadata
            metadata = {
                'name': file_meta.name,
                'size': file_meta.size,
                'createdDateTime': file_meta.createdDateTime,
                'lastModifiedDateTime': file_meta.lastModifiedDateTime,
                'webUrl': file_meta.webUrl,
                'eTag': file_meta.eTag,
                'cTag': file_meta.cTag,
                'checksum_sha256': checksum,
                'download_url': download_url
            }
            
            metadata_file = local_path / f"{self._sanitize_filename(file_meta.name)}.metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            # Update database with new metadata
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
            logger.info(f"        Backed up: {file_meta.name} ({file_meta.size:,} bytes)")
            
            return checksum
            
        except Exception as e:
            logger.warning(f"Error downloading {file_meta.name}: {str(e)}")
            self.stats['files_failed'] += 1
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe filesystem use."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200 - len(ext)] + ext
        
        return filename
    
    def _get_all_files_with_metadata(self, site_id: str, drive_id: str) -> List[FileMetadata]:
        """Get all files in a drive with metadata for change detection."""
        files = []
        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/children"
        
        params = {
            '$select': 'id,name,size,eTag,cTag,lastModifiedDateTime,createdDateTime,webUrl,file,parentReference',
            '$top': 200
        }
        
        try:
            while url:
                response = self._make_graph_request(url, params=params)
                if response.status_code != 200:
                    break
                
                data = response.json()
                items = data.get('value', [])
                
                for item in items:
                    if 'file' in item:
                        file_meta = FileMetadata.from_graph_data(item, drive_id)
                        files.append(file_meta)
                    elif 'folder' in item:
                        folder_id = item.get('id')
                        folder_files = self._get_files_in_folder(site_id, drive_id, folder_id)
                        files.extend(folder_files)
                
                url = data.get('@odata.nextLink')
                params = {}
            
            return files
            
        except Exception as e:
            logger.warning(f"Error getting files: {str(e)}")
            return []
    
    def _get_files_in_folder(self, site_id: str, drive_id: str, folder_id: str) -> List[FileMetadata]:
        """Recursively get all files in a folder."""
        files = []
        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{folder_id}/children"
        
        params = {
            '$select': 'id,name,size,eTag,cTag,lastModifiedDateTime,createdDateTime,webUrl,file,parentReference',
            '$top': 200
        }
        
        try:
            while url:
                response = self._make_graph_request(url, params=params)
                if response.status_code != 200:
                    break
                
                data = response.json()
                items = data.get('value', [])
                
                for item in items:
                    if 'file' in item:
                        file_meta = FileMetadata.from_graph_data(item, drive_id)
                        files.append(file_meta)
                    elif 'folder' in item:
                        subfolder_id = item.get('id')
                        subfolder_files = self._get_files_in_folder(site_id, drive_id, subfolder_id)
                        files.extend(subfolder_files)
                
                url = data.get('@odata.nextLink')
                params = {}
            
            return files
            
        except Exception as e:
            logger.warning(f"Error getting files in folder {folder_id}: {str(e)}")
            return []
    
    def backup_all_sites(self, backup_type: str = 'incremental', max_workers: int = 5):
        """Backup all SharePoint sites with optimized incremental capability."""
        logger.info("=" * 80)
        logger.info(f"Starting OPTIMIZED {backup_type.upper()} tenant-wide SharePoint backup")
        logger.info("=" * 80)
        
        session_id = self.db.start_backup_session(backup_type)
        
        try:
            sites = self._get_all_sites()
            logger.info(f"Found {len(sites)} SharePoint sites")
            
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
                    self.stats['files_failed'] += 1
            
            self.db.update_backup_session(
                session_id=session_id,
                files_backed_up=self.stats['files_backed_up'],
                files_skipped=self.stats['files_skipped'],
                total_size=self.stats['total_size'],
                status='completed'
            )
            
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
    
    def _backup_site(self, site_id: str, site_name: str, site_url: str, 
                    backup_type: str, max_workers: int):
        """Backup a single SharePoint site."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        site_path = self.backup_dir / self._sanitize_filename(site_name) / timestamp
        site_path.mkdir(parents=True, exist_ok=True)
        
        site_metadata = {
            'site_id': site_id,
            'site_name': site_name,
            'site_url': site_url,
            'backup_date': datetime.now().isoformat(),
            'backup_type': backup_type,
            'backup_method': 'Optimized Microsoft Graph API'
        }
        
        metadata_file = site_path / "site_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(site_metadata, f, indent=2)
        
        drives = self._get_site_drives(site_id)
        logger.info(f"    Found {len(drives)} document libraries")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for drive in drives:
                drive_name = drive.get('name', 'Unknown')
                drive_id = drive.get('id')
                
                future = executor.submit(
                    self._backup_drive_optimized,
                    site_id, drive_id, drive_name, site_path, backup_type
                )
                futures.append((drive_name, future))
            
            for drive_name, future in futures:
                try:
                    future.result()
                    logger.info(f"    Completed: {drive_name}")
                except Exception as e:
                    logger.error(f"    Failed to backup drive '{drive_name}': {str(e)}")
    
    def _get_site_drives(self, site_id: str) -> List[Dict[str, Any]]:
        """Get all drives (document libraries) for a site."""
        drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id