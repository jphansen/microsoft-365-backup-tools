#!/usr/bin/env python3
"""
Optimized Exchange Incremental Backup
Leverages Exchange email immutability - emails never change, only new ones are created.
Uses message ID tracking instead of checksum calculations for dramatic performance improvements.
"""

import os
import sys
import json
import argparse
import hashlib
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from loguru import logger
from exchange_checksum_db import ExchangeChecksumDB

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
class EmailMetadata:
    """Email metadata from Graph API for ID-based tracking."""
    id: str
    subject: str
    receivedDateTime: str
    sentDateTime: str
    lastModifiedDateTime: str
    changeKey: str
    size: int
    hasAttachments: bool
    isRead: bool
    importance: str
    from_address: Dict[str, Any]
    toRecipients: List[Dict[str, Any]]
    ccRecipients: List[Dict[str, Any]]
    bccRecipients: List[Dict[str, Any]]
    body: Dict[str, Any]  # Added to store body from batch fetch
    folder_id: str
    folder_name: str
    
    @classmethod
    def from_graph_data(cls, data: Dict[str, Any], folder_id: str = None, folder_name: str = None) -> 'EmailMetadata':
        return cls(
            id=data.get('id'),
            subject=data.get('subject', 'No Subject'),
            receivedDateTime=data.get('receivedDateTime', ''),
            sentDateTime=data.get('sentDateTime', ''),
            lastModifiedDateTime=data.get('lastModifiedDateTime', ''),
            changeKey=data.get('changeKey', ''),  # May be empty if not in query
            size=data.get('size', 0),
            hasAttachments=data.get('hasAttachments', False),
            isRead=data.get('isRead', False),
            importance=data.get('importance', 'normal'),
            from_address=data.get('from', {}),
            toRecipients=data.get('toRecipients', []),
            ccRecipients=data.get('ccRecipients', []),
            bccRecipients=data.get('bccRecipients', []),
            body=data.get('body', {}),  # Get body from batch data
            folder_id=folder_id,
            folder_name=folder_name
        )


class OptimizedExchangeBackup:
    """Optimized Exchange backup using message ID tracking (no checksums needed)."""
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str, 
                 backup_dir: str = None, db_path: str = "backup_checksums_exchange.db"):
        """
        Initialize optimized Exchange backup client.
        
        Args:
            client_id: Azure AD App Client ID
            client_secret: Azure AD App Client Secret
            tenant_id: Azure AD Tenant ID
            backup_dir: Backup directory (defaults to EXCHANGE_BACKUP_DIR or "backup/exchange")
            db_path: Path to checksum database
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        
        # Determine backup directory
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            # Try EXCHANGE_BACKUP_DIR environment variable first
            exchange_backup_dir = os.environ.get('EXCHANGE_BACKUP_DIR')
            if exchange_backup_dir:
                self.backup_dir = Path(exchange_backup_dir)
            else:
                # Fall back to default
                self.backup_dir = Path("backup/exchange")
        
        self.db = ExchangeChecksumDB(db_path)
        
        self.access_token = self._get_access_token()
        self.token_obtained_time = datetime.now()
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        self.session = requests.Session()
        
        self.stats = {
            'emails_backed_up': 0,
            'emails_skipped': 0,
            'attachments_backed_up': 0,
            'attachments_skipped': 0,
            'total_size': 0,
            'bytes_saved': 0,
            'users_processed': 0,
            'start_time': datetime.now()
        }
        
        logger.info(f"Optimized Exchange backup initialized")
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
        
        headers = {**self.headers, **kwargs.pop('headers', {})}
        
        response = self.session.request(method, url, headers=headers, **kwargs)
        
        if response.status_code == 401:
            logger.warning("Token expired, refreshing...")
            self.access_token = self._get_access_token()
            self.token_obtained_time = datetime.now()
            self.headers['Authorization'] = f'Bearer {self.access_token}'
            headers['Authorization'] = f'Bearer {self.access_token}'
            response = self.session.request(method, url, headers=headers, **kwargs)
        
        return response
    
    def _get_users(self) -> List[Dict[str, Any]]:
        """Get list of users to backup."""
        logger.info("Fetching users...")
        
        users = []
        endpoint = "https://graph.microsoft.com/v1.0/users"
        params = {
            '$select': 'id,userPrincipalName,displayName,mail',
            '$top': 999
        }
        
        try:
            while endpoint:
                response = self._make_graph_request(endpoint, params=params)
                response.raise_for_status()
                data = response.json()
                
                users.extend(data.get('value', []))
                endpoint = data.get('@odata.nextLink')
                
                # Reset params after first request
                params = {}
            
            logger.info(f"Found {len(users)} users")
            return users
            
        except Exception as e:
            logger.error(f"Failed to fetch users: {str(e)}")
            return []
    
    def _get_user_folders(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all mail folders for a user."""
        logger.debug(f"Fetching folders for user: {user_id}")
        
        folders = []
        endpoint = f"https://graph.microsoft.com/v1.0/users/{user_id}/mailFolders"
        
        try:
            response = self._make_graph_request(endpoint)
            response.raise_for_status()
            data = response.json()
            
            folders.extend(data.get('value', []))
            
            # Recursively get child folders
            for folder in folders[:]:
                child_folders = self._get_child_folders(user_id, folder['id'])
                folders.extend(child_folders)
            
            return folders
            
        except Exception as e:
            logger.error(f"Failed to fetch folders for user {user_id}: {str(e)}")
            return []
    
    def _get_child_folders(self, user_id: str, parent_folder_id: str) -> List[Dict[str, Any]]:
        """Get child folders for a parent folder."""
        child_folders = []
        endpoint = f"https://graph.microsoft.com/v1.0/users/{user_id}/mailFolders/{parent_folder_id}/childFolders"
        
        try:
            response = self._make_graph_request(endpoint)
            response.raise_for_status()
            data = response.json()
            
            folders = data.get('value', [])
            child_folders.extend(folders)
            
            # Recursively get grandchildren
            for folder in folders:
                grandchildren = self._get_child_folders(user_id, folder['id'])
                child_folders.extend(grandchildren)
            
            return child_folders
            
        except Exception as e:
            logger.debug(f"No child folders or error: {str(e)}")
            return []
    
    def _get_folder_message_ids(self, user_id: str, folder_id: str) -> Set[str]:
        """
        Get ONLY message IDs from a folder (fast).
        Used for quick incremental detection.
        
        Args:
            user_id: User ID
            folder_id: Folder ID
            
        Returns:
            Set of message IDs
        """
        message_ids = set()
        
        # URL encode the folder ID
        import urllib.parse
        encoded_folder_id = urllib.parse.quote(folder_id, safe='')
        endpoint = f"https://graph.microsoft.com/v1.0/users/{user_id}/mailFolders/{encoded_folder_id}/messages"
        
        # Minimal query for speed - IDs only
        params = {
            '$select': 'id',
            '$top': 200,  # Larger batch for IDs
            '$orderby': 'receivedDateTime desc'
        }
        
        try:
            while endpoint:
                response = self._make_graph_request(endpoint, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    batch_messages = data.get('value', [])
                    
                    for msg in batch_messages:
                        if 'id' in msg:
                            message_ids.add(msg['id'])
                    
                    endpoint = data.get('@odata.nextLink')
                    params = {}  # Next link includes all params
                else:
                    logger.warning(f"Failed to get message IDs from folder {folder_id}: {response.status_code}")
                    break
            
            logger.debug(f"Got {len(message_ids)} message IDs from folder {folder_id}")
            return message_ids
            
        except Exception as e:
            logger.error(f"Could not get message IDs from folder {folder_id}: {str(e)}")
            return set()
    
    def _get_email_batch_data(self, user_id: str, folder_id: str, message_ids: Set[str]) -> List[Dict[str, Any]]:
        """
        Get full email data for specific message IDs.
        Only fetch full data for new emails.
        
        Args:
            user_id: User ID
            folder_id: Folder ID
            message_ids: Set of message IDs to fetch
            
        Returns:
            List of message dictionaries with full data
        """
        if not message_ids:
            return []
        
        messages = []
        # We need to fetch emails in batches since Graph API doesn't support bulk by ID
        
        # URL encode the folder ID
        import urllib.parse
        encoded_folder_id = urllib.parse.quote(folder_id, safe='')
        
        # Fetch in smaller batches to avoid timeouts
        batch_size = 50
        message_id_list = list(message_ids)
        
        for i in range(0, len(message_id_list), batch_size):
            batch_ids = message_id_list[i:i + batch_size]
            
            # For each message ID, we need to fetch individually or use filter
            # Graph API doesn't support bulk fetch by multiple IDs easily
            # We'll fetch them one by one but in parallel could be optimized
            
            for message_id in batch_ids:
                try:
                    # Fetch individual email with full data
                    endpoint = f"https://graph.microsoft.com/v1.0/users/{user_id}/messages/{urllib.parse.quote(message_id, safe='')}"
                    params = {
                        '$select': 'id,subject,from,toRecipients,ccRecipients,bccRecipients,receivedDateTime,'
                                  'sentDateTime,hasAttachments,isRead,importance,body,internetMessageHeaders'
                    }
                    
                    response = self._make_graph_request(endpoint, params=params)
                    if response.status_code == 200:
                        messages.append(response.json())
                    else:
                        logger.warning(f"Failed to fetch email {message_id}: {response.status_code}")
                        
                except Exception as e:
                    logger.warning(f"Error fetching email {message_id}: {str(e)}")
            
            # Small delay between batches to avoid rate limiting
            import time
            if i + batch_size < len(message_id_list):
                time.sleep(0.1)
        
        logger.debug(f"Fetched full data for {len(messages)} emails")
        return messages
    
    def _get_email_metadata(self, user_id: str, message_id: str, folder_id: str = None, 
                           folder_name: str = None) -> Optional[EmailMetadata]:
        """Get full email metadata for a specific message."""
        # For emails that can't be accessed individually, try to get basic info
        # from the folder listing that we already have
        
        # First, try the individual message approaches
        endpoints_to_try = []
        
        # Approach 1: No encoding (works for simple IDs)
        endpoints_to_try.append(f"https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}")
        
        # Approach 2: URL encode but keep = unencoded (common in Exchange IDs)
        import urllib.parse
        # Encode everything except = which is common in Exchange message IDs
        encoded_safe = urllib.parse.quote(message_id, safe='=')
        endpoints_to_try.append(f"https://graph.microsoft.com/v1.0/users/{user_id}/messages/{encoded_safe}")
        
        # Approach 3: Full encoding as last resort
        encoded_full = urllib.parse.quote(message_id, safe='')
        endpoints_to_try.append(f"https://graph.microsoft.com/v1.0/users/{user_id}/messages/{encoded_full}")
        
        # Approach 4: Try through folder endpoint
        if folder_id:
            folder_endpoint = f"https://graph.microsoft.com/v1.0/users/{user_id}/mailFolders/{folder_id}/messages/{message_id}"
            endpoints_to_try.append(folder_endpoint)
            
            folder_endpoint_encoded = f"https://graph.microsoft.com/v1.0/users/{user_id}/mailFolders/{folder_id}/messages/{encoded_safe}"
            endpoints_to_try.append(folder_endpoint_encoded)
        
        # Try with absolute minimum query
        minimal_params = {'$select': 'id,subject,receivedDateTime,size,hasAttachments'}
        
        for endpoint in endpoints_to_try:
            try:
                response = self._make_graph_request(endpoint, params=minimal_params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Even if we only get minimal data, that's enough to create metadata
                    # The EmailMetadata class can handle missing fields
                    return EmailMetadata.from_graph_data(data, folder_id, folder_name)
                
            except Exception as e:
                logger.debug(f"Endpoint {endpoint[:50]}... failed: {str(e)}")
                continue
        
        # If we can't get individual metadata, we have a bigger problem
        # These emails might be system-generated or have special access requirements
        logger.error(f"Could not get email metadata for {message_id} after trying {len(endpoints_to_try)} approaches")
        
        # FAIL COMPLETELY - no placeholder
        raise Exception(f"Cannot access email metadata for {message_id}")
    
    def _get_message_attachments(self, user_id: str, message_id: str) -> List[Dict[str, Any]]:
        """Get attachments for a message."""
        attachments = []
        # Try different encoding approaches like we do for metadata
        endpoints_to_try = []
        
        # Approach 1: No encoding
        endpoints_to_try.append(f"https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/attachments")
        
        # Approach 2: URL encode but keep = unencoded
        import urllib.parse
        encoded_safe = urllib.parse.quote(message_id, safe='=')
        endpoints_to_try.append(f"https://graph.microsoft.com/v1.0/users/{user_id}/messages/{encoded_safe}/attachments")
        
        # Approach 3: Full encoding
        encoded_full = urllib.parse.quote(message_id, safe='')
        endpoints_to_try.append(f"https://graph.microsoft.com/v1.0/users/{user_id}/messages/{encoded_full}/attachments")
        
        for endpoint in endpoints_to_try:
            try:
                response = self._make_graph_request(endpoint)
                if response.status_code == 200:
                    data = response.json()
                    attachments.extend(data.get('value', []))
                    return attachments
            except Exception as e:
                logger.debug(f"Attachment endpoint failed: {str(e)}")
                continue
        
        logger.error(f"Failed to fetch attachments for message {message_id} after trying {len(endpoints_to_try)} approaches")
        return attachments
    
    def _download_attachment(self, user_id: str, attachment_id: str, message_id: str) -> Optional[bytes]:
        """Download a specific attachment."""
        # URL encode the message ID since it may contain special characters
        import urllib.parse
        encoded_message_id = urllib.parse.quote(message_id, safe='')
        endpoint = f"https://graph.microsoft.com/v1.0/users/{user_id}/messages/{encoded_message_id}/attachments/{attachment_id}/$value"
        
        try:
            response = self._make_graph_request(endpoint, headers={'Accept': 'application/octet-stream'})
            response.raise_for_status()
            return response.content
            
        except Exception as e:
            logger.error(f"Failed to download attachment {attachment_id}: {str(e)}")
            return None
    
    def _create_eml_file(self, email_meta: EmailMetadata, attachments: List[Dict[str, Any]], 
                        attachment_data: Dict[str, bytes], file_path: Path):
        """Create EML file from email metadata."""
        from email.message import EmailMessage
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        
        eml = MIMEMultipart()
        
        # Set headers
        eml['Subject'] = email_meta.subject
        eml['From'] = self._format_email_address(email_meta.from_address)
        eml['To'] = self._format_email_addresses(email_meta.toRecipients)
        eml['Cc'] = self._format_email_addresses(email_meta.ccRecipients)
        eml['Date'] = email_meta.receivedDateTime
        
        # Get email body from metadata (already fetched in batch)
        body_content = email_meta.body.get('content', '') if email_meta.body else ''
        body_type = email_meta.body.get('contentType', 'text') if email_meta.body else 'text'
        
        logger.debug(f"Using batch-fetched email body: {len(body_content)} characters, type: {body_type}")
        
        # Create body part
        if body_type == 'html':
            body_part = MIMEText(body_content, 'html', 'utf-8')
        else:
            body_part = MIMEText(body_content, 'plain', 'utf-8')
        eml.attach(body_part)
        
        # Add attachments
        for attachment in attachments:
            attachment_id = attachment.get('id')
            if attachment_id in attachment_data:
                content = attachment_data[attachment_id]
                filename = attachment.get('name', f'attachment_{attachment_id}')
                content_type = attachment.get('contentType', 'application/octet-stream')
                
                maintype, subtype = content_type.split('/', 1) if '/' in content_type else (content_type, 'octet-stream')
                attachment_part = MIMEBase(maintype, subtype)
                attachment_part.set_payload(content)
                attachment_part.add_header('Content-Disposition', 'attachment', filename=filename)
                encoders.encode_base64(attachment_part)
                eml.attach(attachment_part)
        
        # Write EML file
        with open(file_path, 'wb') as f:
            f.write(eml.as_bytes())
        
        file_size = file_path.stat().st_size if file_path.exists() else 0
        logger.debug(f"Created EML file: {file_path}, size: {file_size} bytes")
    
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
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename[:100]
    
    def _backup_user_emails(self, user: Dict[str, Any], backup_type: str = 'incremental'):
        """Backup emails for a single user using ID-based tracking."""
        user_id = user.get('id')
        user_email = user.get('userPrincipalName', user.get('mail', 'Unknown'))
        
        logger.info(f"Processing user: {user_email}")
        
        # Get user's mail folders
        folders = self._get_user_folders(user_id)
        logger.info(f"Found {len(folders)} folders for user {user_email}")
        
        # Create user backup directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_backup_path = self.backup_dir / self._sanitize_filename(user_email.split('@')[0]) / timestamp
        user_backup_path.mkdir(parents=True, exist_ok=True)
        
        # Save user metadata
        user_metadata = {
            'user_id': user_id,
            'user_email': user_email,
            'display_name': user.get('displayName', ''),
            'backup_date': datetime.now().isoformat(),
            'backup_type': backup_type
        }
        
        with open(user_backup_path / "user_metadata.json", 'w') as f:
            json.dump(user_metadata, f, indent=2)
        
        # Process each folder
        total_new_emails = 0
        total_skipped_emails = 0
        
        for folder in folders:
            folder_id = folder.get('id')
            folder_name = folder.get('displayName', 'Unknown')
            
            logger.info(f"Processing folder: {folder_name}")
            
            # Create folder directory
            folder_path = user_backup_path / self._sanitize_filename(folder_name)
            folder_path.mkdir(parents=True, exist_ok=True)
            
            # TWO-PHASE APPROACH for performance:
            # Phase 1: Get message IDs only (fast)
            current_message_ids = self._get_folder_message_ids(user_id, folder_id)
            logger.info(f"Found {len(current_message_ids)} emails in folder")
            
            if not current_message_ids:
                continue
            
            # Get already backed up message IDs from database
            existing_records = self.db.get_user_email_records(user_email)
            existing_message_ids = {record['message_id'] for record in existing_records}
            
            # Find new emails (IDs not in database)
            new_message_ids = current_message_ids - existing_message_ids
            skipped_message_ids = current_message_ids & existing_message_ids
            
            logger.info(f"New emails: {len(new_message_ids)}, Skipped: {len(skipped_message_ids)}")
            
            # Phase 2: Get full data only for new emails
            new_emails_in_folder = 0
            skipped_emails_in_folder = len(skipped_message_ids)
            
            if new_message_ids:
                # Fetch full data for new emails
                new_messages = self._get_email_batch_data(user_id, folder_id, new_message_ids)
                
                for message in new_messages:
                    message_id = message.get('id')
                    subject = message.get('subject', 'No Subject')
                    
                    # NEW EMAIL DETECTED - log details
                    logger.info(f"NEW EMAIL DETECTED: '{subject}' (ID: {message_id[:30]}...)")
                    
                    # New email - backup it
                    try:
                        # Create EmailMetadata from the batch data we already have
                        email_meta = EmailMetadata.from_graph_data(message, folder_id, folder_name)
                        logger.debug(f"Created metadata for new email: {subject}")
                        
                        # Now we need to get the email body and attachments
                        self._backup_single_email_with_metadata(
                            user_id, user_email, email_meta, folder_path
                        )
                        new_emails_in_folder += 1
                        total_new_emails += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to backup email '{subject}' ({message_id}): {str(e)}")
            
            total_skipped_emails += skipped_emails_in_folder
            self.stats['bytes_saved'] += skipped_emails_in_folder * 1024  # Approximate savings
            
            logger.info(f"New emails: {new_emails_in_folder}, Skipped: {skipped_emails_in_folder}")
        
        self.stats['emails_backed_up'] += total_new_emails
        self.stats['emails_skipped'] += total_skipped_emails
        self.stats['users_processed'] += 1
        
        logger.info(f"User {user_email}: {total_new_emails} new emails backed up, {total_skipped_emails} skipped")
    
    def _backup_single_email_with_metadata(self, user_id: str, user_email: str, 
                                          email_meta: EmailMetadata, folder_path: Path):
        """Backup a single email using already fetched metadata."""
        message_id = email_meta.id
        subject = email_meta.subject
        
        logger.info(f"Starting backup of email: '{subject}' (ID: {message_id[:30]}...)")
        
        # VALIDATION: Check if we have actual email data
        # If we don't have body content or basic fields, fail completely
        body_content = email_meta.body.get('content', '') if email_meta.body else ''
        
        if not body_content:
            error_msg = f"Email has no body content - batch fetch failed to get email data"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        if subject == 'No Subject' and not body_content:
            error_msg = f"Email has no subject and no body - likely batch fetch issue"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        logger.debug(f"Email validation passed: subject='{subject}', body length={len(body_content)}")
        
        # Get attachments if any
        attachments = []
        attachment_data = {}
        
        if email_meta.hasAttachments:
            logger.debug(f"Email has attachments, fetching attachment list...")
            attachments = self._get_message_attachments(user_id, message_id)
            logger.debug(f"Found {len(attachments)} attachments")
            
            for attachment in attachments:
                attachment_id = attachment.get('id')
                attachment_name = attachment.get('name', f'attachment_{attachment_id}')
                
                # Download attachment
                content = self._download_attachment(user_id, attachment_id, message_id)
                if content:
                    attachment_data[attachment_id] = content
                    self.stats['attachments_backed_up'] += 1
                    self.stats['total_size'] += len(content)
                    logger.debug(f"Downloaded attachment: {attachment_name} ({len(content)} bytes)")
                else:
                    logger.warning(f"Failed to download attachment: {attachment_name}")
                    self.stats['attachments_skipped'] += 1
        
        # Create EML file
        safe_subject = self._sanitize_filename(email_meta.subject)
        safe_message_id = self._sanitize_filename(message_id)
        eml_filename = f"{safe_subject}_{safe_message_id}.eml"
        eml_path = folder_path / eml_filename
        
        logger.debug(f"Creating EML file: {eml_filename}")
        
        self._create_eml_file(email_meta, attachments, attachment_data, eml_path)
        
        # Update database ONLY if we successfully created the EML file
        logger.debug(f"Updating database record for email: {message_id}")
        self.db.update_email_record(
            user_id=user_email,
            message_id=message_id,
            folder_id=email_meta.folder_id,
            folder_name=email_meta.folder_name,
            subject=email_meta.subject,
            sender=self._format_email_address(email_meta.from_address),
            received_date=email_meta.receivedDateTime,
            message_size=email_meta.size + sum(len(c) for c in attachment_data.values()),
            checksum=hashlib.sha256(message_id.encode()).hexdigest(),  # Simple checksum based on ID
            has_attachments=email_meta.hasAttachments,
            attachment_count=len(attachments),
            backup_format='eml',
            backup_path=str(eml_path.parent)
        )
        
        # Update attachment records
        for attachment in attachments:
            attachment_id = attachment.get('id')
            if attachment_id in attachment_data:
                content = attachment_data[attachment_id]
                self.db.update_attachment_record(
                    email_id=message_id,  # This would need the actual email ID from database
                    attachment_id=attachment_id,
                    attachment_name=attachment.get('name', f'attachment_{attachment_id}'),
                    attachment_size=attachment.get('size', 0),
                    checksum=hashlib.sha256(content).hexdigest()
                )
        
        logger.info(f"Successfully backed up: '{subject}'")
    
    def backup_all(self, backup_type: str = 'incremental'):
        """Main backup method."""
        logger.info(f"Starting {backup_type.upper()} Exchange backup")
        logger.info("=" * 60)
        
        session_id = self.db.start_exchange_backup_session(backup_type)
        
        try:
            users = self._get_users()
            logger.info(f"Found {len(users)} users")
            
            for i, user in enumerate(users, 1):
                user_email = user.get('userPrincipalName', user.get('mail', f'User_{i}'))
                logger.info(f"[{i}/{len(users)}] Processing: {user_email}")
                
                try:
                    self._backup_user_emails(user, backup_type)
                except Exception as e:
                    logger.error(f"Failed to backup user {user_email}: {str(e)}")
            
            self.db.update_exchange_backup_session(
                session_id=session_id,
                emails_backed_up=self.stats['emails_backed_up'],
                emails_skipped=self.stats['emails_skipped'],
                attachments_backed_up=self.stats['attachments_backed_up'],
                attachments_skipped=self.stats['attachments_skipped'],
                total_size=self.stats['total_size'],
                status='completed'
            )
            
            self._print_summary()
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}")
            self.db.update_exchange_backup_session(
                session_id=session_id,
                emails_backed_up=self.stats['emails_backed_up'],
                emails_skipped=self.stats['emails_skipped'],
                attachments_backed_up=self.stats['attachments_backed_up'],
                attachments_skipped=self.stats['attachments_skipped'],
                total_size=self.stats['total_size'],
                status='failed',
                error_message=str(e)
            )
            raise
    
    def _print_summary(self):
        """Print backup summary."""
        end_time = datetime.now()
        duration = end_time - self.stats['start_time']
        
        logger.info("=" * 60)
        logger.info("EXCHANGE BACKUP SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Duration: {duration}")
        logger.info(f"Users processed: {self.stats['users_processed']}")
        logger.info(f"Emails backed up: {self.stats['emails_backed_up']}")
        logger.info(f"Emails skipped: {self.stats['emails_skipped']}")
        logger.info(f"Attachments backed up: {self.stats['attachments_backed_up']}")
        logger.info(f"Attachments skipped: {self.stats['attachments_skipped']}")
        logger.info(f"Total size: {self.stats['total_size']:,} bytes")
        logger.info(f"Bytes saved: {self.stats['bytes_saved']:,} bytes")
        
        if self.stats['emails_backed_up'] + self.stats['emails_skipped'] > 0:
            skip_rate = (self.stats['emails_skipped'] / 
                        (self.stats['emails_backed_up'] + self.stats['emails_skipped'])) * 100
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
        logger.warning("python-dotenv not installed. Using system environment variables.")
    except Exception as e:
        logger.warning(f"Failed to load .env file: {str(e)}")
    
    parser = argparse.ArgumentParser(
        description='Optimized Exchange Incremental Backup'
    )
    
    parser.add_argument('--type', choices=['full', 'incremental'], 
                       default='incremental',
                       help='Backup type (default: incremental)')
    
    parser.add_argument('--backup-dir', default=None,
                       help='Backup directory (overrides EXCHANGE_BACKUP_DIR)')
    
    parser.add_argument('--db-path', default='backup_checksums_exchange.db',
                       help='Checksum database path (default: backup_checksums_exchange.db)')
    
    args = parser.parse_args()
    
    # Get credentials from environment
    CLIENT_ID = os.environ.get('EXCHANGE_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('EXCHANGE_CLIENT_SECRET')
    TENANT_ID = os.environ.get('EXCHANGE_TENANT_ID')
    
    if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
        logger.error("Missing credentials! Set EXCHANGE_CLIENT_ID, EXCHANGE_CLIENT_SECRET, EXCHANGE_TENANT_ID")
        logger.error("Example: export EXCHANGE_TENANT_ID='your-tenant-id'")
        sys.exit(1)

    try:
        backup = OptimizedExchangeBackup(
            CLIENT_ID, CLIENT_SECRET, TENANT_ID, 
            args.backup_dir, args.db_path
        )

        backup.backup_all(args.type)

    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
