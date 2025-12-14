# Dataverse Database Backup Tool

A Python tool to backup an entire Microsoft Dataverse (Power Platform) database with all data exported to JSON format.

## Features

- ✅ Backs up all tables (entities) from Dataverse
- ✅ Exports all records with full data
- ✅ Includes table metadata and schemas
- ✅ Saves attribute/column definitions
- ✅ Handles pagination automatically for large datasets
- ✅ JSON output format for easy import/analysis
- ✅ Comprehensive logging and error handling
- ✅ Backup summary with record counts
- ✅ Timestamped backup folders

## Prerequisites

1. **Azure AD App Registration**
   - Register an application in Azure AD
   - Grant Dataverse permissions:
     - `Dynamics CRM user_impersonation` (Delegated)
     - Or add the app as an Application User in Dataverse
   - Create a client secret
   - Grant admin consent for the permissions

2. **Power Platform Environment**
   - Access to a Dataverse environment
   - Environment URL (e.g., `https://org.crm.dynamics.com`)

3. **Python 3.7+**

## Installation

1. Install required packages:
```bash
pip install -r dataverse_requirements.txt
```

2. Set up environment variables:
```bash
export DATAVERSE_ENVIRONMENT_URL="https://org.crm.dynamics.com"
export DATAVERSE_TENANT_ID="your-azure-ad-tenant-id"
export DATAVERSE_CLIENT_ID="your-azure-ad-app-client-id"
export DATAVERSE_CLIENT_SECRET="your-azure-ad-app-client-secret"
export BACKUP_DIR="backup"  # Optional, defaults to "backup"
```

## Usage

### Basic Usage

```bash
python dataverse_backup.py
```

### Using Environment Variables

Create a `.env` file or export variables:

```bash
# Linux/Mac
export DATAVERSE_ENVIRONMENT_URL="https://contoso.crm.dynamics.com"
export DATAVERSE_TENANT_ID="12345678-1234-1234-1234-123456789abc"
export DATAVERSE_CLIENT_ID="87654321-4321-4321-4321-abcdef123456"
export DATAVERSE_CLIENT_SECRET="your-secret-value"

python dataverse_backup.py
```

```powershell
# Windows PowerShell
$env:DATAVERSE_ENVIRONMENT_URL="https://contoso.crm.dynamics.com"
$env:DATAVERSE_TENANT_ID="12345678-1234-1234-1234-123456789abc"
$env:DATAVERSE_CLIENT_ID="87654321-4321-4321-4321-abcdef123456"
$env:DATAVERSE_CLIENT_SECRET="your-secret-value"

python dataverse_backup.py
```

## Azure AD App Setup for Dataverse

### Step-by-Step Guide

1. **Go to Azure Portal** (https://portal.azure.com)

2. **Register a New Application**:
   - Navigate to "Azure Active Directory" > "App registrations"
   - Click "New registration"
   - Name: "Dataverse Backup Tool"
   - Supported account types: "Accounts in this organizational directory only"
   - Click "Register"

3. **Note the Application (client) ID and Tenant ID**:
   - Application (client) ID is your `DATAVERSE_CLIENT_ID`
   - Directory (tenant) ID is your `DATAVERSE_TENANT_ID`

4. **Create a Client Secret**:
   - Go to "Certificates & secrets"
   - Click "New client secret"
   - Description: "Backup Tool Secret"
   - Expiry: Choose appropriate duration
   - Click "Add"
   - **Copy the secret value immediately** (this is your `DATAVERSE_CLIENT_SECRET`)

5. **Grant API Permissions**:
   - Go to "API permissions"
   - Click "Add a permission"
   - Choose "Dynamics CRM"
   - Select "Delegated permissions"
   - Add `user_impersonation`
   - Click "Add permissions"
   - **Click "Grant admin consent"** (requires admin privileges)

6. **Create Application User in Dataverse**:
   - Go to Power Platform Admin Center (https://admin.powerplatform.microsoft.com)
   - Select your environment
   - Go to "Settings" > "Users + permissions" > "Application users"
   - Click "New app user"
   - Select your Azure AD app
   - Assign appropriate security role (System Administrator for full backup)
   - Save

7. **Get your Environment URL**:
   - In Power Platform Admin Center, select your environment
   - Copy the Environment URL (e.g., `https://org.crm.dynamics.com`)
   - This is your `DATAVERSE_ENVIRONMENT_URL`

## Backup Structure

The tool creates backups with the following structure:

```
backup/
└── dataverse_backup_20231201_143022/
    ├── tables_metadata.json          # All tables metadata
    ├── backup_summary.json            # Summary with record counts
    ├── dataverse_backup.log           # Detailed logs
    └── tables/
        ├── account.json               # Account table with all records
        ├── contact.json               # Contact table with all records
        ├── opportunity.json           # Opportunity table with all records
        ├── customentity_abc.json      # Custom tables
        └── ...
```

## JSON Structure

Each table JSON file contains:

```json
{
  "metadata": {
    "LogicalName": "account",
    "DisplayName": "Account",
    "SchemaName": "Account",
    "EntitySetName": "accounts",
    "RecordCount": 150,
    "BackupDate": "2023-12-01T14:30:22.123456",
    "IsCustomEntity": false,
    "PrimaryIdAttribute": "accountid",
    "PrimaryNameAttribute": "name"
  },
  "attributes": [
    {
      "LogicalName": "accountid",
      "SchemaName": "AccountId",
      "DisplayName": "Account",
      "AttributeType": "Uniqueidentifier",
      "IsCustomAttribute": false,
      "IsPrimaryId": true,
      "IsPrimaryName": false,
      "RequiredLevel": "SystemRequired"
    },
    ...
  ],
  "records": [
    {
      "accountid": "12345678-1234-1234-1234-123456789abc",
      "name": "Contoso Ltd",
      "revenue": 1000000,
      "createdon": "2023-01-15T10:30:00Z",
      ...
    },
    ...
  ]
}
```

## Backup Summary

The `backup_summary.json` file provides an overview:

```json
{
  "backup_info": {
    "environment_url": "https://org.crm.dynamics.com",
    "backup_date": "2023-12-01T14:30:22.123456",
    "backup_path": "/full/path/to/backup",
    "total_tables": 45,
    "total_records": 12500
  },
  "tables": [
    {
      "LogicalName": "account",
      "DisplayName": "Account",
      "RecordCount": 150,
      "FileName": "account.json"
    },
    ...
  ]
}
```

## What Gets Backed Up

- **Standard Tables**: All out-of-the-box Dataverse tables (Account, Contact, etc.)
- **Custom Tables**: All custom tables created in your environment
- **All Records**: Every record in each table with all field values
- **Metadata**: Table schemas, attributes, data types
- **Relationships**: Foreign key references preserved in record data

## What Doesn't Get Backed Up

- Binary data (images, files) - only references are backed up
- System/internal tables (filtered by default)
- Audit history
- Plugins/workflows definitions
- Security roles and permissions

## Performance Considerations

- **Large Datasets**: The tool handles pagination automatically (5000 records per page)
- **Rate Limiting**: Dataverse API has rate limits; the tool respects these
- **Backup Time**: Depends on data volume; expect 1-5 minutes per 10,000 records
- **Storage**: JSON files can be large; ensure adequate disk space

## Logging

The tool creates detailed logs:
- Console output for real-time monitoring
- `dataverse_backup.log` file in the backup directory
- Progress indicators for each table

## Troubleshooting

### Authentication Errors
- Verify your Client ID, Client Secret, and Tenant ID are correct
- Ensure admin consent was granted for API permissions
- Check that the application user exists in Dataverse

### Permission Errors
- The application user needs appropriate security role
- For full backup, System Administrator role is recommended
- Check table-level permissions if specific tables fail

### Connection Errors
- Verify the environment URL is correct (use the full URL from Power Platform Admin Center)
- Check your network connection
- Ensure the Dataverse environment is accessible

### Missing Data
- Some system tables are filtered by default (IsValidForAdvancedFind)
- Ensure the security role has read permissions for all required tables

## Restoring Data

To restore data from backup:

1. Parse the JSON files
2. Use Dataverse Web API POST requests to create records
3. Maintain relationship references
4. Handle dependencies (create parent records before child records)

Example restore script structure:
```python
# Read backup file
with open('tables/account.json') as f:
    data = json.load(f)

# Post records back to Dataverse
for record in data['records']:
    # POST to /api/data/v9.2/accounts
    pass
```

## Security Notes

- **Never commit credentials to version control**
- Store credentials in environment variables or Azure Key Vault
- Regularly rotate client secrets
- Use least-privilege access (read-only roles for backups)
- Encrypt backup files if they contain sensitive data
- Secure backup storage location

## Limitations

- API rate limits may slow down very large backups
- Binary/file columns contain references, not actual files
- Some system tables are excluded by design
- Annotations and notes attachments require separate handling

## Advanced Configuration

### Filtering Tables

Modify the `get_tables()` method to filter specific tables:

```python
# Only backup custom tables
tables = [t for t in tables if t.get('IsCustomEntity')]

# Exclude specific tables
exclude = ['systemuser', 'team', 'businessunit']
tables = [t for t in tables if t.get('LogicalName') not in exclude]
```

### Selecting Specific Columns

Modify the `get_table_data()` method to use `$select`:

```python
params = {
    "$select": "accountid,name,revenue",
    "$top": 5000
}
```

### Filtering Records

Add `$filter` to `get_table_data()`:

```python
params = {
    "$filter": "createdon gt 2023-01-01",
    "$top": 5000
}
```

## License

MIT License - Feel free to modify and use as needed.

## Support

For issues related to:
- **Dataverse API**: Check Microsoft Dataverse documentation
- **Authentication**: Verify Azure AD app configuration
- **Performance**: Consider chunking backups by date ranges
- **Restore**: Use Dataverse Web API or Power Platform tools
