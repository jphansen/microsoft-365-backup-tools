#!/usr/bin/env python3
"""
Exchange/Outlook Email Backup Tool
Backs up emails from Exchange Online/Outlook using Microsoft Graph API
Supports:
- Email messages with attachments
- Mailbox folder structure preservation
- Incremental backup using checksum database
- Multiple output formats (EML, JSON, or both)
"""

import os
import sys
import json
import logging
import hashlib
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from email.message import EmailMessage
from email.header import decode_header
import base64
import mimetypes

# Microsoft Graph API client
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Exchange checksum database
from exchange_checksum_db import ExchangeChecksumDB, calculate_email_checksum, calculate_attachment_checksum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('exchange_backup.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class ExchangeBackup:
    """Handles backup operations for Exchange/Outlook emails."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Exchange backup client.
        
        Args:
            config: Configuration dictionary with all settings
        """
        self.config = config
        
        # Authentication
        self.tenant_id = config.get('EXCHANGE_TENANT_ID')
        self.client_id = config.get('EXCHANGE_CLIENT_ID')
        self.client_secret = config.get('EXCHANGE_CLIENT_SECRET')
        
        # Backup settings
        self.backup_dir = Path(config.get('EXCHANGE_BACKUP_DIR', 'backup/exchange'))
        self.user_email = config.get('EXCHANGE_USER_EMAIL')
        self.include_attachments = config.get('EXCHANGE_INCLUDE_ATTACHMENTS', True)
        self.max_emails = config.get('EXCHANGE_MAX_EMAILS_PER_BACKUP', 1000)
        self.preserve_folders = config.get('EXCHANGE_PRESERVE_FOLDER_STRUCTURE', True)
        self.backup_format = config.get('EXCHANGE_BACKUP_FORMAT', 'both')
        self.compress_backups = config.get('EXCHANGE_COMPRESS_BACKUPS', False)
        
        # Graph API settings
        self.graph_endpoint = config.get('EXCHANGE_GRAPH_ENDPOINT', 'https://graph.microsoft.com/v1.0')
        self.batch_size = config.get('EXCHANGE_BATCH_SIZE', 20)
        self.rate_limit_delay = config.get('EXCHANGE_RATE_LIMIT_DELAY', 1)
        self.max_retries = config.get('EXCHANGE_MAX_RETRIES', 3)
        
        # Filtering
        self.filter_date_from = config.get('EXCHANGE_FILTER_DATE_FROM')
        self.filter_date_to = config.get('EXCHANGE_FILTER_DATE_TO')
        self.filter_sender = config.get('EXCHANGE_FILTER_SENDER')
        self.filter_subject = config.get('EXCHANGE_FILTER_SUBJECT')
        
        # Incremental backup
        self.incremental_backup = config.get('EXCHANGE_INCREMENTAL_BACKUP', True)
        self.checksum_db = config.get('EXCHANGE_CHECKSUM_DB', 'backup_checksums_exchange.db')
        
        # Security
        self.encrypt_backups = config.get('EXCHANGE_ENCRYPT_BACKUPS', False)
        self.encryption_password = config.get('EXCHANGE_ENCRYPTION_PASSWORD')
        
        # Advanced settings
        self.request_timeout = config.get('EXCHANGE_REQUEST_TIMEOUT', 30)
        self.max_attachment_size = config.get('EXCHANGE_MAX_ATTACHMENT_SIZE', 4) * 1024 * 1024  # Convert to bytes
        
        # Internal state
        self.access_token = None
        self.session = None
        self.backup_path = None
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_stats = {
            'total_emails': 0,
            'backed_up_emails': 0,
            'skipped_emails': 0,
            'attachments_downloaded': 0,
            'attachments_skipped': 0,
            'errors': 0,
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'users_processed': 0
        }
        
        # Checksum database
        self.checksum_db = ExchangeChecksumDB(self.checksum_db)
        self.backup_session_id = None
        
        # Initialize
        self._setup_session()
        self._authenticate()
        self._setup_backup_directory()
    
    def _setup_session(self):
        """Setup HTTP session with retry logic."""
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
    
    def _authenticate(self):
        """Authenticate with Azure AD to get access token."""
        logger.info("Authenticating with Azure AD...")
        
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        token_data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://graph.microsoft.com/.default',
            'grant_type': 'client_credentials'
        }
        
        try:
            response = self.session.post(token_url, data=token_data, timeout=self.request_timeout)
            response.raise_for_status()
            
            token_response = response.json()
            self.access_token = token_response.get('access_token')
            
            if not self.access_token:
                raise ValueError("No access token received")
            
            logger.info("Authentication successful")
            
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            raise
    
    def _setup_backup_directory(self):
        """Create backup directory structure."""
        if self.user_email:
            # Single user backup
            user_folder = self.user_email.split('@')[0]
            self.backup_path = self.backup_dir / user_folder / self.timestamp
        else:
            # All users backup
            self.backup_path = self.backup_dir / "all_users" / self.timestamp
        
        self.backup_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Backup directory: {self.backup_path}")
    
    def _make_graph_request(self, endpoint: str, method: str = 'GET', **kwargs) -> Dict[str, Any]:
        """
        Make a request to Microsoft Graph API.
        
        Args:
            endpoint: Graph API endpoint (without base URL)
            method: HTTP method
            **kwargs: Additional arguments for requests
            
        Returns:
            Response JSON as dictionary
        """
        url = f"{self.graph_endpoint}{endpoint}"
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Add rate limiting delay
        time.sleep(self.rate_limit_delay)
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                timeout=self.request_timeout,
                **kwargs
            )
            
            response.raise_for_status()
            
            if response.status_code == 204:  # No content
                return {}
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Graph API request failed: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise
    
    def _get_users(self) -> List[Dict[str, Any]]:
        """Get list of users to backup."""
        logger.info("Fetching users...")
        
        if self.user_email:
            # Single user mode
            endpoint = f"/users/{self.user_email}"
            try:
                user_data = self._make_graph_request(endpoint)
                return [user_data]
            except Exception as e:
                logger.error(f"Failed to fetch user {self.user_email}: {str(e)}")
                return []
        
        # All users mode
        users = []
        endpoint = "/users?$select=id,userPrincipalName,displayName,mail"
        
        while endpoint:
            try:
                response = self._make_graph_request(endpoint)
                users.extend(response.get('value', []))
                
                # Check for next page
                endpoint = response.get('@odata.nextLink')
                if endpoint:
                    # Extract just the endpoint part from full URL
                    endpoint = endpoint.replace(self.graph_endpoint, '')
                
            except Exception as e:
                logger.error(f"Failed to fetch users: {str(e)}")
                break
        
        logger.info(f"Found {len(users)} users")
        return users
    
    def _get_user_folders(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all mail folders for a user."""
        logger.debug(f"Fetching folders for user: {user_id}")
        
        folders = []
        endpoint = f"/users/{user_id}/mailFolders"
        
        try:
            response = self._make_graph_request(endpoint)
            folders.extend(response.get('value', []))
            
            # Recursively get child folders
            for folder in folders[:]:  # Copy list to avoid modification during iteration
                child_folders = self._get_child_folders(user_id, folder['id'])
                folders.extend(child_folders)
            
        except Exception as e:
            logger.error(f"Failed to fetch folders for user {user_id}: {str(e)}")
        
        return folders
    
    def _get_child_folders(self, user_id: str, parent_folder_id: str) -> List[Dict[str, Any]]:
        """Get child folders for a parent folder."""
        child_folders = []
        endpoint = f"/users/{user_id}/mailFolders/{parent_folder_id}/childFolders"
        
        try:
            response = self._make_graph_request(endpoint)
            folders = response.get('value', [])
            child_folders.extend(folders)
            
            # Recursively get grandchildren
            for folder in folders:
                grandchildren = self._get_child_folders(user_id, folder['id'])
                child_folders.extend(grandchildren)
            
        except Exception as e:
            logger.debug(f"No child folders or error: {str(e)}")
        
        return child_folders
    
    def _get_folder_messages(self, user_id: str, folder_id: str, skip: int = 0) -> List[Dict[str, Any]]:
        """Get messages from a specific folder."""
        messages = []
        
        # Build query parameters
        params = {
            '$top': self.batch_size,
            '$skip': skip,
            '$select': 'id,subject,from,toRecipients,ccRecipients,bccRecipients,receivedDateTime,'
                      'sentDateTime,hasAttachments,isRead,importance,body,internetMessageHeaders',
            '$orderby': 'receivedDateTime desc'
        }
        
        # Add date filters if specified
        filter_parts = []
        if self.filter_date_from:
            filter_parts.append(f"receivedDateTime ge {self.filter_date_from}T00:00:00Z")
        if self.filter_date_to:
            filter_parts.append(f"receivedDateTime le {self.filter_date_to}T23:59:59Z")
        
        if filter_parts:
            params['$filter'] = ' and '.join(filter_parts)
        
        endpoint = f"/users/{user_id}/mailFolders/{folder_id}/messages"
        
        try:
            response = self._make_graph_request(endpoint, params=params)
            messages.extend(response.get('value', []))
            
            # Check if we need to fetch more (pagination)
            if len(messages) < self.max_emails and '@odata.nextLink' in response:
                next_skip = skip + self.batch_size
                if next_skip < self.max_emails:
                    more_messages = self._get_folder_messages(user_id, folder_id, next_skip)
                    messages.extend(more_messages)
            
        except Exception as e:
            logger.error(f"Failed to fetch messages from folder {folder_id}: {str(e)}")
        
        # Apply additional filters
        filtered_messages = []
        for message in messages:
            if self._apply_message_filters(message):
                filtered_messages.append(message)
        
        return filtered_messages[:self.max_emails]
    
    def _apply_message_filters(self, message: Dict[str, Any]) -> bool:
        """Apply additional filters to messages."""
        # Sender filter
        if self.filter_sender:
            sender = message.get('from', {}).get('emailAddress', {}).get('address', '')
            if not re.search(self.filter_sender, sender, re.IGNORECASE):
                return False
        
        # Subject filter
        if self.filter_subject:
            subject = message.get('subject', '')
            if not re.search(self.filter_subject, subject, re.IGNORECASE):
                return False
        
        # Skip already read if configured
        if self.config.get('EXCHANGE_SKIP_ALREADY_READ', False) and message.get('isRead', False):
            return False
        
        return True
    
    def _get_message_attachments(self, user_id: str, message_id: str) -> List[Dict[str, Any]]:
        """Get attachments for a message."""
        attachments = []
        endpoint = f"/users/{user_id}/messages/{message_id}/attachments"
        
        try:
            response = self._make_graph_request(endpoint)
            attachments.extend(response.get('value', []))
            
        except Exception as e:
            logger.error(f"Failed to fetch attachments for message {message_id}: {str(e)}")
        
        return attachments
    
    def _download_attachment(self, user_id: str, attachment_id: str, message_id: str) -> Optional[bytes]:
        """Download a specific attachment."""
        endpoint = f"/users/{user_id}/messages/{message_id}/attachments/{attachment_id}/$value"
        
        try:
            response = self.session.get(
                f"{self.graph_endpoint}{endpoint}",
                headers={'Authorization': f'Bearer {self.access_token}'},
                timeout=self.request_timeout
            )
            response.raise_for_status()
            
            return response.content
            
        except Exception as e:
            logger.error(f"Failed to download attachment {attachment_id}: {str(e)}")
            return None
    
    def _calculate_checksum(self, message: Dict[str, Any]) -> str:
        """Calculate checksum for a message to detect changes."""
        checksum_data = {
            'id': message.get('id'),
            'lastModifiedDateTime': message.get('lastModifiedDateTime'),
            'body': message.get('body', {}).get('content', ''),
            'hasAttachments': message.get('hasAttachments', False)
        }
        
        # Include attachment metadata if available
        if message.get('hasAttachments', False):
            checksum_data['attachment_count'] = len(message.get('attachments', []))
        
        checksum_string = json.dumps(checksum_data, sort_keys=True)
        return hashlib.sha256(checksum_string.encode()).hexdigest()
    
    def _should_backup_message(self, user_id: str, message: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if a message should be backed up (incremental backup).
        
        Returns:
            Tuple of (should_backup, checksum)
        """
        if not self.incremental_backup:
            return True, calculate_email_checksum(message)
        
        # Use checksum database to check if email has changed
        user_email = self._get_user_email_from_id(user_id)
        message_id = message.get('id')
        current_checksum = calculate_email_checksum(message)
        
        is_unchanged, record = self.checksum_db.is_email_unchanged(
            user_id=user_email,
            message_id=message_id,
            current_checksum=current_checksum
        )
        
        return not is_unchanged, current_checksum
    
    def _get_user_email_from_id(self, user_id: str) -> str:
        """Get user email from user ID."""
        # If we have a specific user email configured, use that
        if self.user_email:
            return self.user_email
        
        # Otherwise, try to extract from user ID or use as-is
        # This is a simple implementation - in production you might want to
        # cache user lookups or handle this differently
        return user_id
    
    def _create_eml_file(self, message: Dict[str, Any], attachments: List[Dict[str, Any]], 
                        attachment_data: Dict[str, bytes], file_path: Path):
        """Create EML file from message data."""
        eml = EmailMessage()
        
        # Headers
        eml['Subject'] = message.get('subject', '')
        eml['From'] = self._format_email_address(message.get('from', {}))
        eml['To'] = self._format_email_addresses(message.get('toRecipients', []))
        eml['Cc'] = self._format_email_addresses(message.get('ccRecipients', []))
        eml['Bcc'] = self._format_email_addresses(message.get('bccRecipients', []))
        eml['Date'] = message.get('receivedDateTime', '')
        
        # Additional headers
        for header in message.get('internetMessageHeaders', []):
            eml[header.get('name', '')] = header.get('value', '')
        
        # Body
        body_content = message.get('body', {}).get('content', '')
        body_type = message.get('body', {}).get('contentType', 'text')
        
        if body_type == 'html':
            eml.set_content(body_content, subtype='html')
        else:
            eml.set_content(body_content)
        
        # Attachments
        for attachment in attachments:
            attachment_id = attachment.get('id')
            if attachment_id in attachment_data:
                content = attachment_data[attachment_id]
                filename = attachment.get('name', f'attachment_{attachment_id}')
                content_type = attachment.get('contentType', 'application/octet-stream')
                
                eml.add_attachment(
                    content,
                    maintype=content_type.split('/')[0],
                    subtype=content_type.split('/')[1] if '/' in content_type else '',
                    filename=filename
                )
        
        # Write EML file
        with open(file_path, 'wb') as f:
            f.write(eml.as_bytes())
    
    def _format_email_address(self, address_dict: Dict[str, Any]) -> str:
        """Format email address from Graph API response."""
        if not address_dict:
            return ''
        
        email_address = address_dict.get('emailAddress', {})
        name = email_address.get('name', '')
        address = email_address.get('address', '')
        
        if name and address:
            return f'"{name}" <{address}>'
        elif address:
            return address
        else:
            return ''
    
    def _format_email_addresses(self, addresses: List[Dict[str, Any]]) -> str:
        """Format list of email addresses."""
        formatted = []
        for addr in addresses:
            formatted.append(self._format_email_address(addr))
        return ', '.join(filter(None, formatted))
    
    def _create_json_file(self, message: Dict[str, Any], attachments: List[Dict[str, Any]], 
                         attachment_data: Dict[str, bytes], file_path: Path):
        """Create JSON file from message data."""
        # Prepare message data for JSON
        json_data = {
            'id': message.get('id'),
            'subject': message.get('subject', ''),
            'from': message.get('from', {}),
            'toRecipients': message.get('toRecipients', []),
            'ccRecipients': message.get('ccRecipients', []),
            'bccRecipients': message.get('bccRecipients', []),
            'receivedDateTime': message.get('receivedDateTime', ''),
            'sentDateTime': message.get('sentDateTime', ''),
            'isRead': message.get('isRead', False),
            'hasAttachments': message.get('hasAttachments', False),
            'importance': message.get('importance', 'normal'),
            'body': message.get('body', {}),
            'internetMessageHeaders': message.get('internetMessageHeaders', []),
            'attachments': [],
            'backup_timestamp': self.timestamp,
            'backup_format': 'json'
        }
        
        # Add attachment metadata
        for attachment in attachments:
            attachment_info = {
                'id': attachment.get('id'),
                'name': attachment.get('name', ''),
                'contentType': attachment.get('contentType', ''),
                'size': attachment.get('size', 0),
                'isInline': attachment.get('isInline', False),
                'contentId': attachment.get('contentId', '')
            }
            
            # Include attachment content if small enough
            attachment_id = attachment.get('id')
            if attachment_id in attachment_data:
                content = attachment_data[attachment_id]
                if len(content) <= 1024 * 1024:  # 1MB limit for embedding
                    attachment_info['content'] = base64.b64encode(content).decode('utf-8')
                else:
                    attachment_info['content'] = 'TOO_LARGE_TO_EMBED'
            
            json_data['attachments'].append(attachment_info)
        
        # Write JSON file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    def _backup_user_messages(self, user: Dict[str, Any]):
        """Backup all messages for a single user."""
        user_id = user.get('id')
        user_email = user.get('userPrincipalName', user.get('mail', 'Unknown'))
        
        logger.info(f"Processing user: {user_email}")
        
        # Get user's mail folders
        folders = self._get_user_folders(user_id)
        logger.info(f"Found {len(folders)} folders for user {user_email}")
        
        user_backup_path = self.backup_path / user_email.split('@')[0]
        if self.preserve_folders:
            user_backup_path.mkdir(parents=True, exist_ok=True)
        
        # Process each folder
        for folder in folders:
            folder_id = folder.get('id')
            folder_name = folder.get('displayName', 'Unknown')
            
            logger.info(f"Processing folder: {folder_name}")
            
            # Create folder directory if preserving structure
            if self.preserve_folders:
                folder_path = user_backup_path / folder_name
                folder_path.mkdir(parents=True, exist_ok=True)
            else:
                folder_path = user_backup_path
            
            # Get messages in folder
            messages = self._get_folder_messages(user_id, folder_id)
            logger.info(f"Found {len(messages)} messages in folder {folder_name}")
            
            # Process each message
            for message in messages:
                self.backup_stats['total_emails'] += 1
                
                try:
                    self._backup_single_message(user_id, message, folder_path)
                    self.backup_stats['backed_up_emails'] += 1
                    
                except Exception as e:
                    logger.error(f"Failed to backup message {message.get('id')}: {str(e)}")
                    self.backup_stats['errors'] += 1
                
                # Check if we've reached the limit
                if self.backup_stats['backed_up_emails'] >= self.max_emails:
                    logger.warning(f"Reached maximum email limit ({self.max_emails})")
                    return
        
        self.backup_stats['users_processed'] += 1
    
    def _backup_single_message(self, user_id: str, message: Dict[str, Any], folder_path: Path):
        """Backup a single email message."""
        message_id = message.get('id')
        subject = message.get('subject', 'No Subject')
        
        # Check if we should backup this message (incremental backup)
        should_backup, checksum = self._should_backup_message(user_id, message)
        
        if not should_backup:
            logger.debug(f"Skipping already backed up message: {subject}")
            self.backup_stats['skipped_emails'] += 1
            return
        
        # Sanitize filename
        safe_subject = re.sub(r'[<>:"/\\|?*]', '_', subject)
        safe_subject = safe_subject[:100]  # Limit length
        
        # Get attachments if needed
        attachments = []
        attachment_data = {}
        
        if self.include_attachments and message.get('hasAttachments', False):
            attachments = self._get_message_attachments(user_id, message_id)
            
            for attachment in attachments:
                attachment_id = attachment.get('id')
                attachment_name = attachment.get('name', f'attachment_{attachment_id}')
                attachment_size = attachment.get('size', 0)
                
                # Check size limit
                if attachment_size > self.max_attachment_size:
                    logger.warning(f"Skipping large attachment: {attachment_name} ({attachment_size} bytes)")
                    self.backup_stats['attachments_skipped'] += 1
                    continue
                
                # Download attachment
                content = self._download_attachment(user_id, attachment_id, message_id)
                if content:
                    attachment_data[attachment_id] = content
                    self.backup_stats['attachments_downloaded'] += 1
        
        # Create backup files based on format
        base_filename = folder_path / f"{safe_subject}_{message_id}"
        
        if self.backup_format in ['eml', 'both']:
            eml_file = base_filename.with_suffix('.eml')
            self._create_eml_file(message, attachments, attachment_data, eml_file)
            logger.debug(f"Created EML file: {eml_file.name}")
        
        if self.backup_format in ['json', 'both']:
            json_file = base_filename.with_suffix('.json')
            self._create_json_file(message, attachments, attachment_data, json_file)
            logger.debug(f"Created JSON file: {json_file.name}")
        
        # Save checksum for incremental backup
        user_email = self._get_user_email_from_id(user_id)
        
        # Calculate total message size
        message_size = len(json.dumps(message, default=str).encode('utf-8'))
        for content in attachment_data.values():
            message_size += len(content)
        
        # Update email record in database
        email_id = self.checksum_db.update_email_record(
            user_id=user_email,
            message_id=message_id,
            folder_id=message.get('parentFolderId'),
            folder_name=folder_path.name if self.preserve_folders else 'root',
            subject=subject,
            sender=self._format_email_address(message.get('from', {})),
            received_date=message.get('receivedDateTime'),
            message_size=message_size,
            checksum=checksum,
            has_attachments=message.get('hasAttachments', False),
            attachment_count=len(attachments),
            backup_format=self.backup_format,
            backup_path=str(base_filename.parent)
        )
        
        # Save attachment checksums if needed
        if self.include_attachments:
            for attachment in attachments:
                attachment_id = attachment.get('id')
                if attachment_id in attachment_data:
                    content = attachment_data[attachment_id]
                    attachment_checksum = calculate_attachment_checksum(content)
                    
                    self.checksum_db.update_attachment_record(
                        email_id=email_id,
                        attachment_id=attachment_id,
                        attachment_name=attachment.get('name', f'attachment_{attachment_id}'),
                        attachment_size=attachment.get('size', 0),
                        checksum=attachment_checksum
                    )
        
        logger.info(f"Backed up: {subject}")
    
    def backup_all(self):
        """Backup emails for all configured users."""
        logger.info("=" * 80)
        logger.info("Starting Exchange/Outlook email backup")
        logger.info("=" * 80)
        
        try:
            # Get users to backup
            users = self._get_users()
            
            if not users:
                logger.error("No users found to backup")
                return
            
            # Backup each user
            for user in users:
                try:
                    self._backup_user_messages(user)
                except Exception as e:
                    logger.error(f"Failed to backup user {user.get('userPrincipalName')}: {str(e)}")
                    self.backup_stats['errors'] += 1
            
            # Finalize backup
            self._finalize_backup()
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}", exc_info=True)
            raise
    
    def _finalize_backup(self):
        """Finalize backup and save statistics."""
        self.backup_stats['end_time'] = datetime.now().isoformat()
        
        # Calculate duration
        start_time = datetime.fromisoformat(self.backup_stats['start_time'])
        end_time = datetime.fromisoformat(self.backup_stats['end_time'])
        duration = end_time - start_time
        self.backup_stats['duration_seconds'] = duration.total_seconds()
        
        # Save statistics
        stats_file = self.backup_path / "backup_statistics.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.backup_stats, f, indent=2, default=str)
        
        # Log summary
        logger.info("=" * 80)
        logger.info("BACKUP COMPLETED")
        logger.info("=" * 80)
        logger.info(f"Total emails processed: {self.backup_stats['total_emails']}")
        logger.info(f"Emails backed up: {self.backup_stats['backed_up_emails']}")
        logger.info(f"Emails skipped: {self.backup_stats['skipped_emails']}")
        logger.info(f"Attachments downloaded: {self.backup_stats['attachments_downloaded']}")
        logger.info(f"Attachments skipped: {self.backup_stats['attachments_skipped']}")
        logger.info(f"Users processed: {self.backup_stats['users_processed']}")
        logger.info(f"Errors: {self.backup_stats['errors']}")
        logger.info(f"Duration: {duration}")
        logger.info(f"Backup location: {self.backup_path.absolute()}")
        logger.info("=" * 80)


def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    config = {}
    
    # Required configuration
    config['EXCHANGE_TENANT_ID'] = os.environ.get('EXCHANGE_TENANT_ID')
    config['EXCHANGE_CLIENT_ID'] = os.environ.get('EXCHANGE_CLIENT_ID')
    config['EXCHANGE_CLIENT_SECRET'] = os.environ.get('EXCHANGE_CLIENT_SECRET')
    
    # Optional configuration with defaults
    config['EXCHANGE_BACKUP_DIR'] = os.environ.get('EXCHANGE_BACKUP_DIR', 'backup/exchange')
    config['EXCHANGE_USER_EMAIL'] = os.environ.get('EXCHANGE_USER_EMAIL')
    config['EXCHANGE_INCLUDE_ATTACHMENTS'] = os.environ.get('EXCHANGE_INCLUDE_ATTACHMENTS', 'true').lower() == 'true'
    config['EXCHANGE_MAX_EMAILS_PER_BACKUP'] = int(os.environ.get('EXCHANGE_MAX_EMAILS_PER_BACKUP', '1000'))
    config['EXCHANGE_PRESERVE_FOLDER_STRUCTURE'] = os.environ.get('EXCHANGE_PRESERVE_FOLDER_STRUCTURE', 'true').lower() == 'true'
    config['EXCHANGE_BACKUP_FORMAT'] = os.environ.get('EXCHANGE_BACKUP_FORMAT', 'both')
    config['EXCHANGE_COMPRESS_BACKUPS'] = os.environ.get('EXCHANGE_COMPRESS_BACKUPS', 'false').lower() == 'true'
    
    # Graph API settings
    config['EXCHANGE_GRAPH_ENDPOINT'] = os.environ.get('EXCHANGE_GRAPH_ENDPOINT', 'https://graph.microsoft.com/v1.0')
    config['EXCHANGE_BATCH_SIZE'] = int(os.environ.get('EXCHANGE_BATCH_SIZE', '20'))
    config['EXCHANGE_RATE_LIMIT_DELAY'] = float(os.environ.get('EXCHANGE_RATE_LIMIT_DELAY', '1'))
    config['EXCHANGE_MAX_RETRIES'] = int(os.environ.get('EXCHANGE_MAX_RETRIES', '3'))
    
    # Filtering
    config['EXCHANGE_FILTER_DATE_FROM'] = os.environ.get('EXCHANGE_FILTER_DATE_FROM')
    config['EXCHANGE_FILTER_DATE_TO'] = os.environ.get('EXCHANGE_FILTER_DATE_TO')
    config['EXCHANGE_FILTER_SENDER'] = os.environ.get('EXCHANGE_FILTER_SENDER')
    config['EXCHANGE_FILTER_SUBJECT'] = os.environ.get('EXCHANGE_FILTER_SUBJECT')
    config['EXCHANGE_SKIP_ALREADY_READ'] = os.environ.get('EXCHANGE_SKIP_ALREADY_READ', 'false').lower() == 'true'
    
    # Incremental backup
    config['EXCHANGE_INCREMENTAL_BACKUP'] = os.environ.get('EXCHANGE_INCREMENTAL_BACKUP', 'true').lower() == 'true'
    config['EXCHANGE_CHECKSUM_DB'] = os.environ.get('EXCHANGE_CHECKSUM_DB', 'backup_checksums_exchange.db')
    
    # Security
    config['EXCHANGE_ENCRYPT_BACKUPS'] = os.environ.get('EXCHANGE_ENCRYPT_BACKUPS', 'false').lower() == 'true'
    config['EXCHANGE_ENCRYPTION_PASSWORD'] = os.environ.get('EXCHANGE_ENCRYPTION_PASSWORD')
    
    # Advanced settings
    config['EXCHANGE_REQUEST_TIMEOUT'] = int(os.environ.get('EXCHANGE_REQUEST_TIMEOUT', '30'))
    config['EXCHANGE_MAX_ATTACHMENT_SIZE'] = int(os.environ.get('EXCHANGE_MAX_ATTACHMENT_SIZE', '4'))
    
    return config


def validate_config(config: Dict[str, Any]) -> bool:
    """Validate configuration."""
    errors = []
    
    # Check required fields
    if not config.get('EXCHANGE_TENANT_ID'):
        errors.append("EXCHANGE_TENANT_ID is required")
    
    if not config.get('EXCHANGE_CLIENT_ID'):
        errors.append("EXCHANGE_CLIENT_ID is required")
    
    if not config.get('EXCHANGE_CLIENT_SECRET'):
        errors.append("EXCHANGE_CLIENT_SECRET is required")
    
    # Check for placeholder values
    if 'your-tenant-id-here' in str(config.get('EXCHANGE_TENANT_ID', '')):
        errors.append("EXCHANGE_TENANT_ID contains placeholder value")
    
    if 'your-client-id-here' in str(config.get('EXCHANGE_CLIENT_ID', '')):
        errors.append("EXCHANGE_CLIENT_ID contains placeholder value")
    
    if 'your-client-secret-here' in str(config.get('EXCHANGE_CLIENT_SECRET', '')):
        errors.append("EXCHANGE_CLIENT_SECRET contains placeholder value")
    
    # Validate backup format
    valid_formats = ['eml', 'json', 'both']
    if config.get('EXCHANGE_BACKUP_FORMAT') not in valid_formats:
        errors.append(f"EXCHANGE_BACKUP_FORMAT must be one of: {', '.join(valid_formats)}")
    
    # Validate numeric values
    try:
        max_emails = config.get('EXCHANGE_MAX_EMAILS_PER_BACKUP', 1000)
        if max_emails < 0:
            errors.append("EXCHANGE_MAX_EMAILS_PER_BACKUP must be positive")
    except ValueError:
        errors.append("EXCHANGE_MAX_EMAILS_PER_BACKUP must be a valid integer")
    
    # Log errors
    if errors:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        return False
    
    return True


def main():
    """Main entry point."""
    # Load configuration
    config = load_config()
    
    # Validate configuration
    if not validate_config(config):
        logger.error("Please fix configuration errors and try again")
        sys.exit(1)
    
    try:
        # Create backup instance and run backup
        backup = ExchangeBackup(config)
        backup.backup_all()
        
    except Exception as e:
        logger.error(f"Backup failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
