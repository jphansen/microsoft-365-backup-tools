#!/usr/bin/env python3
"""
Dataverse Database Backup Tool
Backs up an entire Microsoft Dataverse (Power Platform) database including:
- All tables (entities)
- All records with relationships
- Table metadata and schemas
- Choice/picklist definitions
- Custom attributes
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
from msal import ConfidentialClientApplication

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dataverse_backup.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class DataverseBackup:
    """Handles backup operations for Dataverse databases."""
    
    def __init__(self, environment_url: str, tenant_id: str, client_id: str, 
                 client_secret: str, backup_dir: str = "backup"):
        """
        Initialize Dataverse backup client.
        
        Args:
            environment_url: Dataverse environment URL (e.g., https://org.crm.dynamics.com)
            tenant_id: Azure AD Tenant ID
            client_id: Azure AD App Client ID
            client_secret: Azure AD App Client Secret
            backup_dir: Directory where backups will be stored
        """
        self.environment_url = environment_url.rstrip('/')
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        
        self.backup_dir = Path(backup_dir)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_path = self.backup_dir / f"dataverse_backup_{self.timestamp}"
        
        # Create backup directory
        self.backup_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Backup directory created: {self.backup_path}")
        
        # Authentication
        self.access_token = None
        self.authenticate()
    
    def authenticate(self):
        """Authenticate with Azure AD and get access token."""
        logger.info("Authenticating to Dataverse...")
        
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        scope = [f"{self.environment_url}/.default"]
        
        app = ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=authority
        )
        
        result = app.acquire_token_for_client(scopes=scope)
        
        if "access_token" in result:
            self.access_token = result["access_token"]
            logger.info("Authentication successful")
        else:
            error = result.get("error_description", result.get("error"))
            raise Exception(f"Authentication failed: {error}")
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make authenticated request to Dataverse Web API.
        
        Args:
            endpoint: API endpoint (relative to base URL)
            params: Query parameters
            
        Returns:
            Response JSON data
        """
        url = f"{self.environment_url}/api/data/v9.2/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Prefer": "odata.include-annotations=*"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {endpoint}: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise
    
    def _get_all_pages(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Retrieve all pages of data from paginated API endpoint.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            List of all records across all pages
        """
        all_records = []
        next_link = None
        
        while True:
            if next_link:
                # Use the full URL for next page
                url = next_link
                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                    "OData-MaxVersion": "4.0",
                    "OData-Version": "4.0",
                    "Prefer": "odata.include-annotations=*"
                }
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
            else:
                data = self._make_request(endpoint, params)
            
            records = data.get('value', [])
            all_records.extend(records)
            
            # Check for next page
            next_link = data.get('@odata.nextLink')
            if not next_link:
                break
            
            logger.debug(f"Fetching next page... (total so far: {len(all_records)})")
        
        return all_records
    
    def backup_all(self):
        """Backup entire Dataverse database."""
        logger.info("=" * 80)
        logger.info("Starting full Dataverse database backup")
        logger.info("=" * 80)
        
        try:
            # Get all tables/entities
            tables = self.get_tables()
            logger.info(f"Found {len(tables)} tables to backup")
            
            # Save tables metadata
            self.save_tables_metadata(tables)
            
            # Backup each table's data
            self.backup_all_tables(tables)
            
            # Create summary
            self.create_backup_summary(tables)
            
            logger.info("=" * 80)
            logger.info(f"Backup completed successfully!")
            logger.info(f"Backup location: {self.backup_path.absolute()}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}", exc_info=True)
            raise
    
    def get_tables(self) -> List[Dict]:
        """
        Retrieve all tables (entities) from Dataverse.
        
        Returns:
            List of table metadata
        """
        logger.info("Retrieving tables metadata...")
        
        # Get entity definitions
        params = {
            "$select": "LogicalName,DisplayName,SchemaName,IsCustomEntity,IsManaged,PrimaryIdAttribute,PrimaryNameAttribute,EntitySetName,Description",
            "$filter": "IsValidForAdvancedFind eq true and IsPrivate eq false"
        }
        
        tables = self._get_all_pages("EntityDefinitions", params)
        
        # Filter out system tables if desired (optional)
        user_tables = [
            t for t in tables 
            if not t.get('LogicalName', '').startswith('msdyn_') or t.get('IsCustomEntity')
        ]
        
        logger.info(f"Retrieved {len(tables)} tables ({len(user_tables)} user/custom tables)")
        return tables
    
    def save_tables_metadata(self, tables: List[Dict]):
        """Save tables metadata to JSON file."""
        logger.info("Saving tables metadata...")
        
        metadata_path = self.backup_path / "tables_metadata.json"
        
        # Simplify metadata for readability
        simplified_tables = []
        for table in tables:
            # Safely get DisplayName with nested access
            display_name_obj = table.get('DisplayName')
            display_name = None
            if display_name_obj and isinstance(display_name_obj, dict):
                user_localized_label = display_name_obj.get('UserLocalizedLabel')
                if user_localized_label and isinstance(user_localized_label, dict):
                    display_name = user_localized_label.get('Label')
            
            # Safely get Description with nested access
            description_obj = table.get('Description')
            description = None
            if description_obj and isinstance(description_obj, dict):
                desc_user_localized_label = description_obj.get('UserLocalizedLabel')
                if desc_user_localized_label and isinstance(desc_user_localized_label, dict):
                    description = desc_user_localized_label.get('Label')
            
            simplified_tables.append({
                'LogicalName': table.get('LogicalName'),
                'DisplayName': display_name,
                'SchemaName': table.get('SchemaName'),
                'IsCustomEntity': table.get('IsCustomEntity'),
                'IsManaged': table.get('IsManaged'),
                'PrimaryIdAttribute': table.get('PrimaryIdAttribute'),
                'PrimaryNameAttribute': table.get('PrimaryNameAttribute'),
                'EntitySetName': table.get('EntitySetName'),
                'Description': description
            })
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(simplified_tables, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Tables metadata saved to {metadata_path}")
    
    def backup_all_tables(self, tables: List[Dict]):
        """
        Backup data from all tables.
        
        Args:
            tables: List of table metadata
        """
        logger.info("Starting table data backup...")
        
        tables_dir = self.backup_path / "tables"
        tables_dir.mkdir(exist_ok=True)
        
        success_count = 0
        error_count = 0
        
        for idx, table in enumerate(tables, 1):
            logical_name = table.get('LogicalName')
            entity_set_name = table.get('EntitySetName')
            
            # Safely get DisplayName with nested access
            display_name_obj = table.get('DisplayName')
            display_name = logical_name  # default to logical name
            if display_name_obj and isinstance(display_name_obj, dict):
                user_localized_label = display_name_obj.get('UserLocalizedLabel')
                if user_localized_label and isinstance(user_localized_label, dict):
                    display_name = user_localized_label.get('Label', logical_name)
            
            if not entity_set_name:
                logger.warning(f"Skipping {logical_name} - no EntitySetName")
                continue
            
            logger.info(f"[{idx}/{len(tables)}] Backing up table: {display_name} ({logical_name})")
            
            try:
                # Get table attributes/columns metadata
                attributes = self.get_table_attributes(logical_name)
                
                # Get table data
                records = self.get_table_data(entity_set_name)
                
                # Save to JSON
                table_data = {
                    'metadata': {
                        'LogicalName': logical_name,
                        'DisplayName': display_name,
                        'SchemaName': table.get('SchemaName'),
                        'EntitySetName': entity_set_name,
                        'RecordCount': len(records),
                        'BackupDate': datetime.now().isoformat(),
                        'IsCustomEntity': table.get('IsCustomEntity'),
                        'PrimaryIdAttribute': table.get('PrimaryIdAttribute'),
                        'PrimaryNameAttribute': table.get('PrimaryNameAttribute')
                    },
                    'attributes': attributes,
                    'records': records
                }
                
                # Safe filename
                safe_name = logical_name.replace('/', '_').replace('\\', '_')
                table_file = tables_dir / f"{safe_name}.json"
                
                with open(table_file, 'w', encoding='utf-8') as f:
                    json.dump(table_data, f, indent=2, ensure_ascii=False, default=str)
                
                logger.info(f"  ✓ Saved {len(records)} records to {safe_name}.json")
                success_count += 1
                
            except Exception as e:
                logger.error(f"  ✗ Failed to backup table '{logical_name}': {str(e)}")
                error_count += 1
        
        logger.info(f"Table backup completed: {success_count} successful, {error_count} errors")
    
    def get_table_attributes(self, logical_name: str) -> List[Dict]:
        """
        Get attributes/columns metadata for a table.
        
        Args:
            logical_name: Table logical name
            
        Returns:
            List of attribute metadata
        """
        try:
            endpoint = f"EntityDefinitions(LogicalName='{logical_name}')/Attributes"
            params = {
                "$select": "LogicalName,SchemaName,DisplayName,AttributeType,IsCustomAttribute,IsPrimaryId,IsPrimaryName,RequiredLevel,Description"
            }
            
            attributes = self._get_all_pages(endpoint, params)
            
            # Simplify attribute metadata
            simplified_attributes = []
            for attr in attributes:
                # Safely get DisplayName with nested access
                display_name_obj = attr.get('DisplayName')
                display_name = None
                if display_name_obj and isinstance(display_name_obj, dict):
                    user_localized_label = display_name_obj.get('UserLocalizedLabel')
                    if user_localized_label and isinstance(user_localized_label, dict):
                        display_name = user_localized_label.get('Label')
                
                # Safely get RequiredLevel
                required_level_obj = attr.get('RequiredLevel')
                required_level = None
                if required_level_obj and isinstance(required_level_obj, dict):
                    required_level = required_level_obj.get('Value')
                
                # Safely get Description with nested access
                description_obj = attr.get('Description')
                description = None
                if description_obj and isinstance(description_obj, dict):
                    desc_user_localized_label = description_obj.get('UserLocalizedLabel')
                    if desc_user_localized_label and isinstance(desc_user_localized_label, dict):
                        description = desc_user_localized_label.get('Label')
                
                simplified_attributes.append({
                    'LogicalName': attr.get('LogicalName'),
                    'SchemaName': attr.get('SchemaName'),
                    'DisplayName': display_name,
                    'AttributeType': attr.get('AttributeType'),
                    'IsCustomAttribute': attr.get('IsCustomAttribute'),
                    'IsPrimaryId': attr.get('IsPrimaryId'),
                    'IsPrimaryName': attr.get('IsPrimaryName'),
                    'RequiredLevel': required_level,
                    'Description': description
                })
            
            return simplified_attributes
            
        except Exception as e:
            logger.warning(f"Could not retrieve attributes for {logical_name}: {str(e)}")
            return []
    
    def get_table_data(self, entity_set_name: str, top: int = 5000) -> List[Dict]:
        """
        Get all records from a table.
        
        Args:
            entity_set_name: Entity set name for the table
            top: Number of records per page
            
        Returns:
            List of records
        """
        try:
            params = {
                "$top": top
            }
            
            records = self._get_all_pages(entity_set_name, params)
            return records
            
        except Exception as e:
            logger.error(f"Error fetching data from {entity_set_name}: {str(e)}")
            return []
    
    def create_backup_summary(self, tables: List[Dict]):
        """Create a summary of the backup operation."""
        logger.info("Creating backup summary...")
        
        # Count records in each backed up table
        tables_dir = self.backup_path / "tables"
        table_files = list(tables_dir.glob("*.json"))
        
        total_records = 0
        table_summary = []
        
        for table_file in table_files:
            try:
                with open(table_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    record_count = len(data.get('records', []))
                    total_records += record_count
                    
                    table_summary.append({
                        'LogicalName': data['metadata']['LogicalName'],
                        'DisplayName': data['metadata']['DisplayName'],
                        'RecordCount': record_count,
                        'FileName': table_file.name
                    })
            except Exception as e:
                logger.warning(f"Could not read {table_file.name}: {str(e)}")
        
        # Sort by record count
        table_summary.sort(key=lambda x: x['RecordCount'], reverse=True)
        
        summary = {
            'backup_info': {
                'environment_url': self.environment_url,
                'backup_date': datetime.now().isoformat(),
                'backup_path': str(self.backup_path.absolute()),
                'total_tables': len(table_files),
                'total_records': total_records
            },
            'tables': table_summary
        }
        
        summary_path = self.backup_path / "backup_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Backup summary saved: {len(table_files)} tables, {total_records:,} total records")


def main():
    """Main entry point."""
    # Try to load environment variables from .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("Loaded environment variables from .env file")
    except ImportError:
        logger.warning("python-dotenv not installed. Using system environment variables.")
    except Exception as e:
        logger.warning(f"Failed to load .env file: {str(e)}")
    
    # Configuration - Load from environment variables
    ENVIRONMENT_URL = os.environ.get('DATAVERSE_ENVIRONMENT_URL')
    TENANT_ID = os.environ.get('DATAVERSE_TENANT_ID')
    CLIENT_ID = os.environ.get('DATAVERSE_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('DATAVERSE_CLIENT_SECRET')
    BACKUP_DIR = os.environ.get('BACKUP_DIR', 'backup')
    
    # Validate configuration
    missing_vars = []
    if not ENVIRONMENT_URL:
        missing_vars.append('DATAVERSE_ENVIRONMENT_URL')
    if not TENANT_ID:
        missing_vars.append('DATAVERSE_TENANT_ID')
    if not CLIENT_ID:
        missing_vars.append('DATAVERSE_CLIENT_ID')
    if not CLIENT_SECRET:
        missing_vars.append('DATAVERSE_CLIENT_SECRET')
    
    if missing_vars:
        logger.error("Missing required environment variables!")
        logger.error("Please set the following environment variables:")
        for var in missing_vars:
            logger.error(f"  {var}")
        logger.error("\nYou can set them in a .env.dataverse file and run with:")
        logger.error("  uv run --env-file .env.dataverse dataverse_backup.py")
        logger.error("\nOr set them directly:")
        logger.error("  export DATAVERSE_ENVIRONMENT_URL=https://your-environment.crm.dynamics.com")
        logger.error("  export DATAVERSE_TENANT_ID=your-tenant-id")
        logger.error("  export DATAVERSE_CLIENT_ID=your-client-id")
        logger.error("  export DATAVERSE_CLIENT_SECRET=your-client-secret")
        sys.exit(1)
    
    # Log configuration (without revealing secrets)
    logger.info(f"Environment URL: {ENVIRONMENT_URL}")
    logger.info(f"Tenant ID: {TENANT_ID}")
    logger.info(f"Client ID: {CLIENT_ID}")
    logger.info(f"Client Secret: {'*' * len(CLIENT_SECRET) if CLIENT_SECRET else 'NOT SET'}")
    
    try:
        # Create backup instance and run backup
        backup = DataverseBackup(
            environment_url=ENVIRONMENT_URL,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            backup_dir=BACKUP_DIR
        )
        backup.backup_all()
        
    except Exception as e:
        logger.error(f"Backup failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
