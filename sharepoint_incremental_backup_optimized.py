#!/usr/bin/env python3
"""
Optimized SharePoint Incremental Backup with Server-Side Metadata
Uses Microsoft Graph API's eTag, cTag, and lastModifiedDateTime to detect changes
without downloading files unnecessarily.
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
from typing import List, Dict, Any, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import time

# Import loguru for enhanced logging
from loguru import logger

# Import our checksum database
from checksum_db import BackupChecksumDB, calculate_stream_checksum

# Configure loguru with custom levels and formatting
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
            'files_failed': 0,
            'total_size': 0,
            'api_calls': 0,
            'bytes_saved': 0,  # Bytes not downloaded due to change detection
            'start_time': datetime.now()
        }
        
        # Cache for file metadata to avoid redundant API calls
        self.file_metadata_cache: Dict[str, FileMetadata] = {}
        
        logger.info(f"Optimized incremental backup initialized")
        logger.debug(f"Database: {db_path}")
        logger.debug(f"Backup directory: {backup_dir}")
    
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
        """Refresh token if it's about to expire (older than 50 minutes)."""
        current_time = datetime.now()
        time_since_token = current_time - self.token_obtained_time
        
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
    
    def backup_all_sites(self, backup_type: str = 'incremental', max_workers: int = 5):
        """
        Backup all SharePoint sites with optimized incremental capability.
        
        Args:
            backup_type: 'full' or 'incremental'
            max_workers: Maximum number of parallel downloads
        """
        logger.info("=" * 80)
        logger.info(f"Starting OPTIMIZED {backup_type.upper()} tenant-wide SharePoint backup")
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
                    self.stats['files_failed'] += 1
            
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
            'backup_method': 'Optimized Microsoft Graph API (Server-Side Metadata)'
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
                    self._backup_drive_optimized,
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
                    self.stats['files_failed'] += 1
    
    def _get_site_drives(self, site_id: str) -> List[Dict[str, Any]]:
        """Get all drives (document libraries) for a site."""
        drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        
        try:
            response = self._make_graph_request(drives_url)
            if response.status_code == 200:
                return response.json().get('value', [])
            else:
                logger.warning(f"Could not get drives for site {site_id}: {response.status_code}")
                return []
        except Exception as e:
            logger.warning(f"Error getting drives for site {site_id}: {str(e)}")
            return []
    
    def _backup_drive_optimized(self, site_id: str, drive_id: str, drive_name: str, 
                               site_path: Path, backup_type: str):
        """Optimized backup of a document library (drive)."""
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
        
        # Get all files in drive with metadata for change detection
        logger.info(f"        Scanning drive '{drive_name}' for changes...")
        files_to_process = self._get_all_files_with_metadata(site_id, drive_id)
        logger.info(f"        Found {len(files_to_process)} files in drive")
        
        # Process files with optimized logic
        changed_files = []
        unchanged_files = []
        
        for file_meta in files_to_process:
            if backup_type == 'full':
                changed_files.append(file_meta)
                continue
            
            # Check if file has changed using server-side metadata
            if self._has_file_changed(file_meta):
                changed_files.append(file_meta)
            else:
                unchanged_files.append(file_meta)
                self.stats['bytes_saved'] += file_meta.size
        
        logger.info(f"        Changed files: {len(changed_files)}")
        logger.info(f"        Unchanged files: {len(unchanged_files)}")
        logger.info(f"        Bytes saved: {self.stats['bytes_saved']:,}")
        
        # Download changed files
        for file_meta in changed_files:
            try:
                self._download_file_with_checksum(site_id, drive_id, file_meta, drive_path)
            except Exception as e:
                logger.warning(f"        Error downloading {file_meta.name}: {str(e)}")
                self.stats['files_failed'] += 1
    
    def _get_all_files_with_metadata(self, site_id: str, drive_id: str) -> List[FileMetadata]:
        """
        Get all files in a drive with metadata for change detection.
        Uses delta query if available for incremental scanning.
        """
        files = []
        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root/children"
        
        # Include metadata fields for change detection
        params = {
            '$select': 'id,name,size,eTag,cTag,lastModifiedDateTime,createdDateTime,webUrl,file,parentReference',
            '$top': 200  # Batch size
        }
        
        try:
            while url:
                response = self._make_graph_request(url, params=params)
                if response.status_code != 200:
                    break
                
                data = response.json()
                items = data.get('value', [])
                
                for item in items:
                    if 'file' in item:  # It's a file, not a folder
                        file_meta = FileMetadata.from_graph_data(item, drive_id)
                        files.append(file_meta)
                        # Cache metadata
                        self.file_metadata_cache[file_meta.file_path] = file_meta
                    elif 'folder' in item:
                        # Recursively get files in subfolders
                        folder_id = item.get('id')
                        folder_files = self._get_files_in_folder(site_id, drive_id, folder_id)
                        files.extend(folder_files)
                
                url = data.get('@odata.nextLink')
                params = {}  # Next link includes all params
            
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
                response = self