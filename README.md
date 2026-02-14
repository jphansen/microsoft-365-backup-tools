# Microsoft 365 Backup Tools

Backup tools for Microsoft 365 services including Dataverse (Power Platform) and SharePoint.

## Features

- **Dataverse Backup**: Full backup of Dataverse databases including all tables, records, and metadata
- **SharePoint Backup**: Backup SharePoint sites, lists, and documents
- **Incremental Backups**: Track changes and backup only modified data using checksum-based deduplication
- **Multiple Authentication Methods**: User authentication and app registration for SharePoint
- **Graph API Support**: Modern SharePoint backup using Microsoft Graph API
- **Compression**: Optional compression to save storage space
- **Logging**: Comprehensive logging for monitoring and troubleshooting

## Installation with UV

This project uses [UV](https://github.com/astral-sh/uv) for Python package management.

### 1. Install UV (if not already installed)

```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone and setup the project

```bash
# Clone the repository
git clone <repository-url>
cd microsoft-365-backup-tools

# Create virtual environment and install dependencies
uv sync
```

## Configuration

### Dataverse Backup

1. **Create Azure AD App Registration**:
   - Go to Azure Portal → Azure Active Directory → App registrations
   - Create a new app registration
   - Add API permissions: `Dataverse/user_impersonation` (delegated)
   - Create a client secret

2. **Create Application User in Dataverse**:
   - In Power Platform Admin Center, create an application user
   - Assign appropriate security roles (System Administrator recommended for full backup)

3. **Create `.env.dataverse` file**:
   ```bash
   cp .env.dataverse.example .env.dataverse
   ```
   
   Edit `.env.dataverse` with your credentials:
   ```
   DATAVERSE_ENVIRONMENT_URL=https://your-environment.crm.dynamics.com
   DATAVERSE_TENANT_ID=your-tenant-id
   DATAVERSE_CLIENT_ID=your-client-id
   DATAVERSE_CLIENT_SECRET=your-client-secret
   BACKUP_DIR=backup
   ```

### SharePoint Backup

1. **Create `.env.sharepoint` file**:
   ```bash
   cp .env.sharepoint.example .env.sharepoint
   ```
   
   Edit `.env.sharepoint` with your credentials.

## Usage

### Dataverse Backup

```bash
# Test environment variables
uv run --env-file .env.dataverse test_env.py

# Run full backup
uv run --env-file .env.dataverse dataverse_backup.py
```

### SharePoint Backup

#### Basic Backup
```bash
# Run basic SharePoint backup
uv run --env-file .env.sharepoint sharepoint_backup.py
```

#### Incremental Backup with Checksum Deduplication
```bash
# First time: Run full backup to populate checksum database
uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --type full

# Subsequent runs: Incremental backup (only changed files)
uv run --env-file .env.sharepoint sharepoint_incremental_backup.py

# View backup statistics
uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --stats
```

#### Graph API Backup (Modern)
```bash
# Backup using Microsoft Graph API
uv run --env-file .env.sharepoint sharepoint_graph_backup.py
```

#### User Authentication Backup
```bash
# Backup using user authentication
uv run --env-file .env.sharepoint sharepoint_backup_user_auth.py
```

### Demo Script

A demonstration script is available to verify the UV setup:

```bash
python demo_uv_project.py
```

## Project Structure

```
.
├── dataverse_backup.py          # Main Dataverse backup script
├── sharepoint_backup.py         # Main SharePoint backup script
├── test_env.py                  # Environment variable test script
├── pyproject.toml              # Project configuration (UV)
├── requirements.txt            # Legacy requirements file
├── dataverse_requirements.txt  # Dataverse-specific requirements
├── .env.dataverse.example      # Dataverse environment template
├── .env.sharepoint.example     # SharePoint environment template
├── README.md                   # This file
└── backup/                     # Backup output directory
    └── dataverse_backup_YYYYMMDD_HHMMSS/
        ├── tables_metadata.json
        ├── backup_summary.json
        └── tables/
            ├── account.json
            ├── contact.json
            └── ...
```

## Backup Output

Each backup creates a timestamped directory with:
- `tables_metadata.json`: Metadata for all tables
- `backup_summary.json`: Summary of backup with record counts
- `tables/`: Individual JSON files for each table

## Scheduling Backups

### Linux/macOS (cron)

```bash
# Edit crontab
crontab -e

# Add line to run backup daily at 2 AM
0 2 * * * cd /path/to/microsoft-365-backup-tools && uv run --env-file .env.dataverse dataverse_backup.py
```

### Windows (Task Scheduler)

Create a scheduled task to run:
```
cmd /c "cd C:\path\to\microsoft-365-backup-tools && uv run --env-file .env.dataverse dataverse_backup.py"
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**:
   - Verify Azure AD app has correct permissions
   - Check application user has security roles in Dataverse
   - Ensure client secret hasn't expired

2. **Permission Errors**:
   - Application user needs appropriate security roles
   - For SharePoint, ensure app has correct Graph API permissions

3. **Environment Variables Not Loading**:
   - Verify `.env.dataverse` file exists and has correct values
   - Test with `uv run --env-file .env.dataverse test_env.py`

### Logs

Check `dataverse_backup.log` for detailed logs:
```bash
tail -f dataverse_backup.log
```

## Additional Documentation

### SharePoint Backup Documentation
- **[INCREMENTAL_BACKUP_README.md](INCREMENTAL_BACKUP_README.md)**: Complete guide to incremental backup with checksum deduplication
- **[SHAREPOINT_APP_REGISTRATION_GUIDE.md](SHAREPOINT_APP_REGISTRATION_GUIDE.md)**: Step-by-step guide for Azure AD app registration
- **[modern_sharepoint_solution.md](modern_sharepoint_solution.md)**: Modern SharePoint backup solution using Graph API
- **[tenant_wide_backup_solution.md](tenant_wide_backup_solution.md)**: Tenant-wide backup solution architecture

### Test Scripts
The project includes comprehensive test scripts for various components:
- `test_graph_backup.py`: Test Microsoft Graph API backup functionality
- `test_incremental_backup.py`: Test incremental backup logic and checksum database
- `test_sharepoint_auth.py`: Test SharePoint authentication methods
- `test_site_access.py`: Test site access permissions
- `test_tenant_access.py`: Test tenant-wide access
- `test_user_auth.py`: Test user authentication backup

### Utility Scripts
- `check_app_permissions.py`: Check application permissions in Azure AD
- `checksum_db.py`: SQLite database for checksum tracking
- `decode_permissions.py`: Decode and analyze permission scopes
- `diagnose_sharepoint_access.py`: Diagnose SharePoint access issues
- `get_service_principal.py`: Get service principal information
- `grant_access_final.ps1`: PowerShell script to grant SharePoint access
- `grant_sharepoint_access.ps1`: PowerShell script for SharePoint permissions

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Submit a pull request