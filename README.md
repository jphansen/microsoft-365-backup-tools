# Microsoft 365 Backup Tools

Backup tools for Microsoft 365 services including Dataverse (Power Platform), SharePoint, and Exchange/Outlook.

## Features

- **Dataverse Backup**: Full backup of Dataverse databases including all tables, records, and metadata
- **SharePoint Incremental Backup**: Backup SharePoint sites with checksum-based deduplication (only changed files)
- **Exchange/Outlook Incremental Backup**: Backup emails with automatic mailbox discovery and incremental backup
- **Checksum Databases**: Track changes and backup only modified data using SQLite databases
- **Microsoft Graph API**: Modern backup using Microsoft Graph API for SharePoint and Exchange
- **Multiple Output Formats**: EML, JSON, or both for email backups
- **Comprehensive Logging**: Detailed logging for monitoring and troubleshooting

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

### SharePoint Incremental Backup

1. **Create Azure AD App Registration for SharePoint**:
   - Go to Azure Portal → Azure Active Directory → App registrations
   - Create a new app registration or use existing
   - Add Microsoft Graph API permissions:
     - **Sites.Read.All** (Application) - Required for reading SharePoint sites
     - **User.Read.All** (Application) - Required for user enumeration
   - Grant admin consent for all permissions
   - Create a client secret

2. **Create `.env.sharepoint` file**:
   ```bash
   cp .env.sharepoint.example .env.sharepoint
   ```
   
   Edit `.env.sharepoint` with your credentials:
   ```
   SHAREPOINT_CLIENT_ID=your-client-id
   SHAREPOINT_CLIENT_SECRET=your-client-secret
   BACKUP_DIR=backup
   ```

### Exchange/Outlook Incremental Backup

1. **Update Azure AD App Registration**:
   - Go to your existing app registration (or create a new one)
   - Add Microsoft Graph API permissions:
     - **Mail.Read** (Application) - Required for reading emails
     - **Mail.ReadWrite** (Application) - Optional, for marking emails as backed up
     - **MailboxSettings.Read** (Application) - Optional, for mailbox settings
     - **User.Read.All** (Application) - Required for user enumeration
   - Grant admin consent for all permissions

2. **Create `.env.exchange` file**:
   ```bash
   cp .env.exchange.example .env.exchange
   ```
   
   Edit `.env.exchange` with your credentials:
   ```
   # Azure AD Configuration
   EXCHANGE_TENANT_ID=your-tenant-id
   EXCHANGE_CLIENT_ID=your-client-id
   EXCHANGE_CLIENT_SECRET=your-client-secret
   
   # Backup Settings
   EXCHANGE_BACKUP_DIR=backup/exchange
   EXCHANGE_USER_EMAIL=user@yourdomain.com  # Optional: Specific user to backup
   EXCHANGE_INCLUDE_ATTACHMENTS=true
   EXCHANGE_MAX_EMAILS_PER_BACKUP=0  # 0 means unlimited
   EXCHANGE_BACKUP_FORMAT=both  # eml, json, or both
   ```

## Usage

### Dataverse Backup

```bash
# Run full Dataverse backup
uv run --env-file .env.dataverse dataverse_backup.py
```

### SharePoint Incremental Backup

```bash
# First time: Run full backup to populate checksum database
uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --type full

# Subsequent runs: Incremental backup (only changed files)
uv run --env-file .env.sharepoint sharepoint_incremental_backup.py

# View backup statistics
uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --stats

# Cleanup old records (keep last 90 days)
uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --cleanup 90
```

### Exchange/Outlook Incremental Backup

```bash
# Run incremental Exchange/Outlook backup
uv run --env-file .env.exchange exchange_incremental_backup.py

# Run full backup (first time)
uv run --env-file .env.exchange exchange_incremental_backup.py --type full

# View backup statistics
uv run --env-file .env.exchange exchange_incremental_backup.py --stats

# Cleanup old records (keep last 90 days)
uv run --env-file .env.exchange exchange_incremental_backup.py --cleanup 90

# Backup with specific options
uv run --env-file .env.exchange exchange_incremental_backup.py \
  --backup-dir backup/exchange \
  --max-emails 1000 \
  --no-attachments \
  --format json
```

## Project Structure

```
.
├── ARCHIVE/                          # Archived scripts and documentation
├── backup/                           # Backup output directory
├── checksum_db.py                    # SharePoint checksum database
├── dataverse_backup.py               # Dataverse backup script
├── dataverse_requirements.txt        # Dataverse-specific requirements
├── exchange_backup.py                # Exchange backup core module
├── exchange_checksum_db.py           # Exchange checksum database
├── exchange_incremental_backup.py    # Exchange incremental backup script
├── sharepoint_incremental_backup.py  # SharePoint incremental backup script
├── .env.dataverse.example            # Dataverse environment template
├── .env.example                      # General environment template
├── .env.exchange                     # Exchange environment configuration
├── .env.exchange.example             # Exchange environment template
├── .env.sharepoint                   # SharePoint environment configuration
├── .env.sharepoint.example           # SharePoint environment template
├── .gitignore                        # Git ignore file
├── pyproject.toml                    # Project configuration (UV)
├── README.md                         # This file
├── requirements.txt                  # Python requirements
├── backup_checksums.db               # SharePoint checksum database file
├── backup_checksums_exchange.db      # Exchange checksum database file
└── uv.lock                           # UV lock file
```

## Backup Output

### Dataverse Backup
Creates a timestamped directory with:
- `tables_metadata.json`: Metadata for all tables
- `backup_summary.json`: Summary of backup with record counts
- `tables/`: Individual JSON files for each table

### SharePoint Incremental Backup
Creates organized directory structure:
- `backup/[Site Name]/[Timestamp]/`: Site backup with metadata
- `backup_checksums.db`: SQLite database tracking file checksums

### Exchange/Outlook Incremental Backup
Creates organized directory structure:
- `backup/exchange/[User]/[Folder]/`: Email backups with attachments
- `backup_checksums_exchange.db`: SQLite database tracking email checksums

## Scheduling Backups

### Linux/macOS (cron)

```bash
# Edit crontab
crontab -e

# Add lines to run incremental backups daily at 2 AM
0 2 * * * cd /path/to/microsoft-365-backup-tools && uv run --env-file .env.sharepoint sharepoint_incremental_backup.py
0 3 * * * cd /path/to/microsoft-365-backup-tools && uv run --env-file .env.exchange exchange_incremental_backup.py
0 4 * * 0 cd /path/to/microsoft-365-backup-tools && uv run --env-file .env.dataverse dataverse_backup.py
```

### Windows (Task Scheduler)

Create scheduled tasks to run:
```
cmd /c "cd C:\path\to\microsoft-365-backup-tools && uv run --env-file .env.sharepoint sharepoint_incremental_backup.py"
cmd /c "cd C:\path\to\microsoft-365-backup-tools && uv run --env-file .env.exchange exchange_incremental_backup.py"
cmd /c "cd C:\path\to\microsoft-365-backup-tools && uv run --env-file .env.dataverse dataverse_backup.py"
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**:
   - Verify Azure AD app has correct permissions
   - Check client secret hasn't expired
   - Ensure admin consent has been granted for all permissions

2. **Permission Errors**:
   - Application needs appropriate API permissions
   - For SharePoint: Sites.Read.All and User.Read.All
   - For Exchange: Mail.Read and User.Read.All
   - For Dataverse: Dataverse/user_impersonation

3. **Environment Variables Not Loading**:
   - Verify `.env.*` files exist and have correct values
   - Check file permissions and encoding

### Logs

Check log files for detailed information:
- `sharepoint_incremental_backup.log` - SharePoint backup logs
- `exchange_incremental_backup.log` - Exchange backup logs  
- `dataverse_backup.log` - Dataverse backup logs

## Archived Files

Unused scripts, test files, and documentation have been moved to the `ARCHIVE/` directory for reference. These include:
- Legacy backup scripts
- Test scripts
- Detailed documentation guides
- PowerShell scripts
- Example shell scripts

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Submit a pull request