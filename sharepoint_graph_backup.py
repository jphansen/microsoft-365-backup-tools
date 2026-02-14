#!/usr/bin/env python3
"""
SharePoint Tenant-Wide Backup using Microsoft Graph API
This works NOW because Graph API already has tenant-wide permissions.
No need to visit appinv.aspx for each site!
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sharepoint_graph_backup.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class SharePointGraphBackup:
    """Backup all SharePoint sites using Microsoft Graph API."""
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str, backup_dir: str = "backup"):
        """
        Initialize Graph API backup client.
        
        Args:
            client_id: Azure AD App Client ID
            client_secret: Azure AD App Client Secret
            tenant_id: Azure AD Tenant ID
            backup_dir: Directory where backups will be stored
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.backup_dir = Path(backup_dir)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_path = self.backup_dir / f"sharepoint_tenant_backup_{self.timestamp}"
        
        # Get access token
        self.access_token = self._get_access_token()
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        # Create backup directory
        self.backup_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Backup directory created: {self.backup_path}")
    
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
            logger.info("✅ Successfully obtained Graph API access token")
            return token
        except Exception as e:
            logger.error(f"❌ Failed to get access token: {str(e)}")
            raise
    
    def backup_all_sites(self):
        """Backup all SharePoint sites in the tenant."""
        logger.info("=" * 80)
        logger.info("Starting tenant-wide SharePoint backup via Graph API")
        logger.info("=" * 80)
        
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
                    self._backup_site(site_id, site_name, site_url)
                except Exception as e:
                    logger.error(f"Failed to backup site '{site_name}': {str(e)}")
            
            logger.info("=" * 80)
            logger.info(f"✅ Tenant-wide backup completed!")
            logger.info(f"📁 Backup location: {self.backup_path.absolute()}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}", exc_info=True)
            raise
    
    def _get_all_sites(self) -> List[Dict[str, Any]]:
        """Get all SharePoint sites in the tenant."""
        sites_url = "https://graph.microsoft.com/v1.0/sites?$select=id,name,webUrl,displayName,createdDateTime,lastModifiedDateTime"
        all_sites = []
        
        try:
            while sites_url:
                response = requests.get(sites_url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                all_sites.extend(data.get('value', []))
                sites_url = data.get('@odata.nextLink')
            
            return all_sites
        except Exception as e:
            logger.error(f"Failed to get sites: {str(e)}")
            return []
    
    def _backup_site(self, site_id: str, site_name: str, site_url: str):
        """Backup a single SharePoint site."""
        site_path = self.backup_path / self._sanitize_filename(site_name)
        site_path.mkdir(parents=True, exist_ok=True)
        
        # Save site metadata
        site_metadata = {
            'site_id': site_id,
            'site_name': site_name,
            'site_url': site_url,
            'backup_date': datetime.now().isoformat(),
            'backup_method': 'Microsoft Graph API'
        }
        
        metadata_file = site_path / "site_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(site_metadata, f, indent=2)
        
        # Get and backup document libraries (drives)
        drives = self._get_site_drives(site_id)
        logger.info(f"    Found {len(drives)} document libraries")
        
        for drive in drives:
            drive_name = drive.get('name', 'Unknown')
            drive_id = drive.get('id')
            
            logger.info(f"    Processing library: {drive_name}")
            self._backup_drive(site_id, drive_id, drive_name, site_path)
    
    def _get_site_drives(self, site_id: str) -> List[Dict[str, Any]]:
        """Get all drives (document libraries) for a site."""
        drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        
        try:
            response = requests.get(drives_url, headers=self.headers)
            if response.status_code == 200:
                return response.json().get('value', [])
            else:
                logger.warning(f"Could not get drives for site {site_id}: {response.status_code}")
                return []
        except Exception as e:
            logger.warning(f"Error getting drives: {str(e)}")
            return []
    
    def _backup_drive(self, site_id: str, drive_id: str, drive_name: str, site_path: Path):
        """Backup a document library (drive)."""
        drive_path = site_path / self._sanitize_filename(drive_name)
        drive_path.mkdir(parents=True, exist_ok=True)
        
        # Get drive metadata
        drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}"
        try:
            response = requests.get(drive_url, headers=self.headers)
            if response.status_code == 200:
                drive_info = response.json()
                metadata_file = drive_path / "drive_metadata.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(drive_info, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not get drive metadata: {str(e)}")
        
        # Backup root folder
        self._backup_folder(site_id, drive_id, "root", drive_path)
    
    def _backup_folder(self, site_id: str, drive_id: str, folder_id: str, local_path: Path):
        """Recursively backup a folder and its contents."""
        try:
            # Get folder children
            children_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{folder_id}/children"
            response = requests.get(children_url, headers=self.headers)
            
            if response.status_code != 200:
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
                    self._backup_folder(site_id, drive_id, item_id, subfolder_path)
                else:
                    # Download file
                    self._download_file(site_id, drive_id, item_id, item_name, item, local_path)
                    
        except Exception as e:
            logger.warning(f"Error processing folder: {str(e)}")
    
    def _download_file(self, site_id: str, drive_id: str, item_id: str, filename: str, item_data: Dict, local_path: Path):
        """Download a file from SharePoint."""
        try:
            # Download file content
            download_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{item_id}/content"
            response = requests.get(download_url, headers=self.headers, stream=True)
            
            if response.status_code == 200:
                file_path = local_path / self._sanitize_filename(filename)
                
                # Save file
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # Save file metadata
                metadata = {
                    'name': item_data.get('name'),
                    'size': item_data.get('size'),
                    'createdDateTime': item_data.get('createdDateTime'),
                    'lastModifiedDateTime': item_data.get('lastModifiedDateTime'),
                    'webUrl': item_data.get('webUrl'),
                    'download_url': download_url
                }
                
                metadata_file = local_path / f"{self._sanitize_filename(filename)}.metadata.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2)
                
                logger.info(f"        Downloaded: {filename} ({item_data.get('size', 0)} bytes)")
            else:
                logger.warning(f"        Failed to download {filename}: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"        Error downloading {filename}: {str(e)}")
    
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


def main():
    """Main entry point."""
    # Configuration from environment variables
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    TENANT_ID = "163506f6-ef0e-42f8-a823-d13d7563bad9"  # Your tenant ID
    BACKUP_DIR = os.environ.get('BACKUP_DIR', 'backup')
    
    # Validate configuration
    if not CLIENT_ID or not CLIENT_SECRET:
        logger.error("Please configure SharePoint credentials!")
        logger.error("Set the following environment variables:")
        logger.error("  SHAREPOINT_CLIENT_ID - Azure AD App Client ID")
        logger.error("  SHAREPOINT_CLIENT_SECRET - Azure AD App Client Secret")
        logger.error("  BACKUP_DIR (optional) - Backup directory path")
        sys.exit(1)
    
    try:
        # Create backup instance and run backup
        backup = SharePointGraphBackup(CLIENT_ID, CLIENT_SECRET, TENANT_ID, BACKUP_DIR)
        backup.backup_all_sites()
        
    except Exception as e:
        logger.error(f"Backup failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()