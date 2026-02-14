#!/usr/bin/env python3
"""
SharePoint Site Backup Tool - USER AUTHENTICATION VERSION
Uses user credentials instead of app-only authentication.
This often works better when SharePoint app-only access is problematic.
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext
from office365.sharepoint.files.file import File
from office365.sharepoint.listitems.listitem import ListItem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sharepoint_backup_user.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class SharePointBackupUserAuth:
    """Handles backup operations for SharePoint sites using USER authentication."""
    
    def __init__(self, site_url: str, username: str, password: str, backup_dir: str = "backup"):
        """
        Initialize SharePoint backup client with USER authentication.
        
        Args:
            site_url: Full URL to the SharePoint site (e.g., https://yourtenant.sharepoint.com/sites/yoursite)
            username: User email (e.g., user@yourtenant.onmicrosoft.com)
            password: User password
            backup_dir: Directory where backups will be stored
        """
        self.site_url = site_url
        self.backup_dir = Path(backup_dir)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_path = self.backup_dir / f"sharepoint_backup_{self.timestamp}"
        
        # Authenticate with USER credentials
        logger.info(f"Authenticating to SharePoint site: {site_url}")
        logger.info(f"Using user: {username}")
        
        try:
            credentials = UserCredential(username, password)
            self.ctx = ClientContext(site_url).with_credentials(credentials)
            
            # Test authentication immediately
            web = self.ctx.web
            self.ctx.load(web, ["Title"])
            self.ctx.execute_query()
            
            logger.info(f"✅ Successfully authenticated! Connected to site: {web.properties['Title']}")
            
        except Exception as e:
            logger.error(f"❌ Authentication failed: {str(e)}")
            logger.error("\nTroubleshooting tips:")
            logger.error("1. Check username and password are correct")
            logger.error("2. Ensure user has access to the SharePoint site")
            logger.error("3. Check if MFA is enabled (disable for this user or use app password)")
            logger.error("4. Verify the site URL is correct")
            raise
        
        # Create backup directory
        self.backup_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Backup directory created: {self.backup_path}")
    
    def backup_all(self):
        """Backup entire SharePoint site."""
        logger.info("=" * 80)
        logger.info("Starting full SharePoint site backup (User Auth)")
        logger.info("=" * 80)
        
        try:
            # Backup document libraries
            self.backup_document_libraries()
            
            # Backup lists
            self.backup_lists()
            
            # Backup site metadata
            self.backup_site_metadata()
            
            logger.info("=" * 80)
            logger.info(f"✅ Backup completed successfully!")
            logger.info(f"📁 Backup location: {self.backup_path.absolute()}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"❌ Backup failed: {str(e)}", exc_info=True)
            raise
    
    def backup_document_libraries(self):
        """Backup all document libraries in the site."""
        logger.info("Backing up document libraries...")
        
        web = self.ctx.web
        lists = web.lists
        self.ctx.load(lists)
        self.ctx.execute_query()
        
        doc_lib_count = 0
        for list_obj in lists:
            # Check if it's a document library
            if list_obj.properties.get('BaseTemplate') == 101:  # Document Library
                lib_title = list_obj.properties['Title']
                logger.info(f"Processing document library: {lib_title}")
                
                try:
                    self.backup_library(list_obj)
                    doc_lib_count += 1
                except Exception as e:
                    logger.error(f"Failed to backup library '{lib_title}': {str(e)}")
        
        logger.info(f"Backed up {doc_lib_count} document libraries")
    
    def backup_library(self, list_obj):
        """Backup a single document library."""
        lib_title = list_obj.properties['Title']
        lib_path = self.backup_path / "DocumentLibraries" / lib_title
        lib_path.mkdir(parents=True, exist_ok=True)
        
        # Get root folder
        root_folder = list_obj.root_folder
        self.ctx.load(root_folder)
        self.ctx.execute_query()
        
        # Backup files and folders recursively
        self._backup_folder(root_folder, lib_path)
    
    def _backup_folder(self, folder, local_path: Path):
        """Recursively backup a folder and its contents."""
        try:
            # Load folder properties
            self.ctx.load(folder)
            self.ctx.execute_query()
            
            folder_name = folder.properties.get('Name', '')
            logger.debug(f"Processing folder: {folder_name}")
            
            # Get all files in folder
            files = folder.files
            self.ctx.load(files)
            self.ctx.execute_query()
            
            # Download each file
            for file in files:
                try:
                    file_name = file.properties['Name']
                    file_path = local_path / file_name
                    
                    logger.info(f"Downloading: {file_name}")
                    
                    # Download file content
                    response = File.open_binary(self.ctx, file.serverRelativeUrl)
                    
                    # Save file
                    with open(file_path, 'wb') as local_file:
                        local_file.write(response.content)
                    
                    # Save file metadata
                    metadata = {
                        'Name': file.properties.get('Name'),
                        'ServerRelativeUrl': file.properties.get('ServerRelativeUrl'),
                        'TimeCreated': str(file.properties.get('TimeCreated')),
                        'TimeLastModified': str(file.properties.get('TimeLastModified')),
                        'Length': file.properties.get('Length'),
                        'Author': file.properties.get('Author'),
                        'ModifiedBy': file.properties.get('ModifiedBy')
                    }
                    
                    metadata_path = local_path / f"{file_name}.metadata.json"
                    with open(metadata_path, 'w') as meta_file:
                        json.dump(metadata, meta_file, indent=2)
                    
                except Exception as e:
                    logger.error(f"Failed to download file '{file_name}': {str(e)}")
            
            # Get all subfolders
            folders = folder.folders
            self.ctx.load(folders)
            self.ctx.execute_query()
            
            # Recursively backup subfolders
            for subfolder in folders:
                subfolder_name = subfolder.properties.get('Name', '')
                
                # Skip system folders
                if subfolder_name.startswith('_'):
                    continue
                
                subfolder_path = local_path / subfolder_name
                subfolder_path.mkdir(parents=True, exist_ok=True)
                
                self._backup_folder(subfolder, subfolder_path)
                
        except Exception as e:
            logger.error(f"Error processing folder: {str(e)}")
    
    def backup_lists(self):
        """Backup all lists (non-document libraries) in the site."""
        logger.info("Backing up lists...")
        
        web = self.ctx.web
        lists = web.lists
        self.ctx.load(lists)
        self.ctx.execute_query()
        
        lists_path = self.backup_path / "Lists"
        lists_path.mkdir(parents=True, exist_ok=True)
        
        list_count = 0
        for list_obj in lists:
            # Skip document libraries (BaseTemplate 101)
            base_template = list_obj.properties.get('BaseTemplate')
            if base_template == 101:
                continue
            
            # Skip hidden lists
            if list_obj.properties.get('Hidden', False):
                continue
            
            list_title = list_obj.properties['Title']
            logger.info(f"Processing list: {list_title}")
            
            try:
                self.backup_list(list_obj, lists_path)
                list_count += 1
            except Exception as e:
                logger.error(f"Failed to backup list '{list_title}': {str(e)}")
        
        logger.info(f"Backed up {list_count} lists")
    
    def backup_list(self, list_obj, lists_path: Path):
        """Backup a single list with all its items."""
        list_title = list_obj.properties['Title']
        
        # Get list items
        items = list_obj.items
        self.ctx.load(items)
        self.ctx.execute_query()
        
        # Collect all items data
        items_data = []
        for item in items:
            items_data.append(dict(item.properties))
        
        # Save list metadata
        list_metadata = {
            'Title': list_obj.properties.get('Title'),
            'Description': list_obj.properties.get('Description'),
            'BaseTemplate': list_obj.properties.get('BaseTemplate'),
            'ItemCount': list_obj.properties.get('ItemCount'),
            'Created': str(list_obj.properties.get('Created')),
            'LastItemModifiedDate': str(list_obj.properties.get('LastItemModifiedDate')),
        }
        
        # Save to JSON file
        list_data = {
            'metadata': list_metadata,
            'items': items_data
        }
        
        safe_filename = "".join(c for c in list_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        list_file = lists_path / f"{safe_filename}.json"
        
        with open(list_file, 'w', encoding='utf-8') as f:
            json.dump(list_data, f, indent=2, default=str)
        
        logger.info(f"Saved list '{list_title}' with {len(items_data)} items")
    
    def backup_site_metadata(self):
        """Backup general site metadata."""
        logger.info("Backing up site metadata...")
        
        web = self.ctx.web
        self.ctx.load(web)
        self.ctx.execute_query()
        
        metadata = {
            'Title': web.properties.get('Title'),
            'Description': web.properties.get('Description'),
            'Url': web.properties.get('Url'),
            'Created': str(web.properties.get('Created')),
            'LastItemModifiedDate': str(web.properties.get('LastItemModifiedDate')),
            'Language': web.properties.get('Language'),
            'WebTemplate': web.properties.get('WebTemplate'),
            'BackupDate': datetime.now().isoformat(),
        }
        
        metadata_file = self.backup_path / "site_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        logger.info("Site metadata saved")


def main():
    """Main entry point for user authentication version."""
    # Configuration - Use USER credentials instead of app credentials
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL', 'https://yourtenant.sharepoint.com/sites/yoursite')
    USERNAME = os.environ.get('SHAREPOINT_USERNAME', 'user@yourtenant.onmicrosoft.com')
    PASSWORD = os.environ.get('SHAREPOINT_PASSWORD', 'your-password')
    BACKUP_DIR = os.environ.get('BACKUP_DIR', 'backup')
    
    # Validate configuration
    if 'yourtenant' in SITE_URL or 'user@' in USERNAME:
        logger.error("Please configure the SharePoint USER credentials!")
        logger.error("Set the following environment variables:")
        logger.error("  SHAREPOINT_SITE_URL - Full URL to your SharePoint site")
        logger.error("  SHAREPOINT_USERNAME - User email with site access")
        logger.error("  SHAREPOINT_PASSWORD - User password")
        logger.error("  BACKUP_DIR (optional) - Backup directory path")
        logger.error("\nNote: This version uses USER authentication, not app-only.")
        sys.exit(1)
    
    try:
        # Create backup instance and run backup
        backup = SharePointBackupUserAuth(SITE_URL, USERNAME, PASSWORD, BACKUP_DIR)
        backup.backup_all()
        
    except Exception as e:
        logger.error(f"Backup failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()