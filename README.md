# Microsoft 365 Backup Tools

Backup tools for Microsoft 365 services including Dataverse (Power Platform), SharePoint, and Exchange/Outlook.

## Features

- **Dataverse Backup**: Full backup of Dataverse databases including all tables, records, and metadata
- **SharePoint Incremental Backup**: Backup SharePoint sites with checksum-based deduplication (only changed files)
- **Exchange/Outlook Incremental Backup**: Backup emails with automatic mailbox discovery and incremental backup
- **Checksum Databases**: Track changes and backup only modified data using SQLite databases
- **Database Rebuild Tools**: Reconstruct checksum databases from existing backup files without cloud access
- **Microsoft Graph API**: Modern backup using Microsoft Graph API for SharePoint and Exchange
- **Multiple Output Formats**: EML, JSON, or both for email backups
- **Comprehensive Logging**: Detailed logging with Loguru for monitoring and troubleshooting

## Recent Improvements

### Enhanced Logging (February 2026)
- **Loguru Integration**: All backup scripts now use `loguru` for professional logging
- **Custom Log Levels**: TRACE (🔍), DEBUG (🐛), INFO (ℹ️), SUCCESS (✅), WARNING (⚠️), ERROR (❌), CRITICAL (💥)
- **Colored Console Output**: Easy-to-read colored logs with icons
- **File Logging**: Automatic log rotation (10 MB), retention (30 days), and compression (zip)
- **Verbosity Control**: Environment variable `LOGURU_LEVEL` controls log detail

### Exchange Backup Improvements (February 2026)
- **Unlimited Email Backup by Default**: `--max-emails` now defaults to 0 (unlimited) instead of 1000
- **Automatic Token Refresh**: Tokens automatically refresh during long-running backups
  - Proactive refresh at 50 minutes (before 60-90 minute expiration)
  - Automatic retry on 401 errors with token refresh
  - Enables 24+ hour backup runs without token expiration issues
- **Better User Experience**: Shows "unlimited" instead of "0" in backup summary

### Optimized Exchange Incremental Backup (February 2026)
- **Two-Phase Performance Optimization**: Dramatically faster incremental backups
  - **Phase 1**: Fast message ID detection (IDs only, no email content)
  - **Phase 2**: Selective full data fetch (only for new emails)
  - **Result**: 2-10x faster than previous implementation
- **Message ID Tracking**: Leverages Exchange email immutability
  - Emails never change, only new ones are created
  - Uses message IDs instead of checksum calculations
  - Dramatically reduces API calls and processing time
- **No Placeholders**: Proper error handling
  - Fails completely if email can't be downloaded
  - No database entries for failed emails
  - Failed emails get retried next backup run
  - No empty EML files or fake backups
- **Email Validation**: Ensures actual email content
  - Validates email has body content before creating EML
  - Fails if batch fetch doesn't get proper data
  - Prevents creation of empty or incomplete backups
- **Reliable Email Body Fetch**: Uses proven batch fetch approach
  - Gets email bodies in batch requests (like the old script)
  - Works for all email types including system folders
  - No individual email fetch failures

### Database Rebuild Tools (February 2026)
- **Offline Database Reconstruction**: Rebuild checksum databases from existing backup files without cloud access
- **SharePoint Database Rebuild**: Reconstruct `backup_checksums.db` from local SharePoint backup files
- **Exchange Database Rebuild**: Reconstruct `backup_checksums_exchange.db` from local Exchange backup files
- **Metadata Extraction**: Extract email metadata from EML/JSON files for Exchange backups
- **Dry Run Mode**: Test database rebuild without making changes
- **Flexible Paths**: Support custom backup directories and database locations

### Performance Optimizations (February 2026)
- **Optimized SharePoint Backup**: `sharepoint_incremental_optimized.py` - Uses server-side metadata (eTag/cTag) for 15-30x faster backups
- **Optimized Exchange Backup**: `exchange_incremental_optimized.py` - Uses message ID tracking for 10-100x faster backups
- **Enhanced Checksum Database**: `checksum_db_enhanced.py` - Extended database with eTag/cTag support and performance metrics
- **Performance Documentation**: `OPTIMIZATION_README.md` - Detailed guide on performance optimizations

### Unified Configuration (Earlier)
- **Single `.env` File**: All services now use unified environment configuration
- **Simplified Setup**: One configuration file for Dataverse, SharePoint, and Exchange
- **Backward Compatible**: Legacy `.env.*` files still supported

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

### Unified Environment Configuration

All backup tools now use a single `.env` file for configuration. This simplifies setup and ensures consistency across all services.

1. **Create the unified `.env` file**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your credentials for all services:
   ```
   # Microsoft 365 Backup Tools - Unified Environment Configuration
   
   # COMMON CONFIGURATION
   BACKUP_DIR=backup
   
   # SHAREPOINT BACKUP CONFIGURATION
   SHAREPOINT_SITE_URL=https://yourtenant.sharepoint.com/sites/yoursite
   SHAREPOINT_TENANT_ID=your-tenant-id-here
   SHAREPOINT_CLIENT_ID=your-client-id-here
   SHAREPOINT_CLIENT_SECRET=your-client-secret-here
   
   # EXCHANGE BACKUP CONFIGURATION
   EXCHANGE_TENANT_ID=your-tenant-id-here
   EXCHANGE_CLIENT_ID=your-client-id-here
   EXCHANGE_CLIENT_SECRET=your-client-secret-here
   EXCHANGE_BACKUP_DIR=backup/exchange
   
   # DATAVERSE BACKUP CONFIGURATION
   DATAVERSE_ENVIRONMENT_URL=https://org.crm.dynamics.com
   DATAVERSE_TENANT_ID=your-tenant-id-here
   DATAVERSE_CLIENT_ID=your-client-id-here
   DATAVERSE_CLIENT_SECRET=your-client-secret-here
   ```

### Azure AD App Registration Setup

#### Option 1: Single App for All Services (Recommended)
Create one Azure AD app with all required permissions:

1. **Create Azure AD App Registration**:
   - Go to Azure Portal → Azure Active Directory → App registrations
   - Create a new app registration
   - Add Microsoft Graph API permissions:
     - **Sites.Read.All** (Application) - For SharePoint backup
     - **Mail.Read** (Application) - For Exchange backup
     - **User.Read.All** (Application) - For user enumeration
   - Add Dataverse permission:
     - **Dataverse/user_impersonation** (Delegated)
   - Grant admin consent for all permissions
   - Create a client secret

2. **Create Application User in Dataverse** (if backing up Dataverse):
   - In Power Platform Admin Center, create an application user
   - Assign appropriate security roles (System Administrator recommended for full backup)

#### Option 2: Separate Apps for Each Service
Create separate Azure AD apps for each service if you prefer to isolate permissions.

### Legacy Configuration Files

For backward compatibility, the old `.env.*` files are still supported:
- `.env.dataverse` - Dataverse-specific configuration
- `.env.sharepoint` - SharePoint-specific configuration  
- `.env.exchange` - Exchange-specific configuration

However, the unified `.env` file is recommended for new installations.

## Usage

### Using the Unified .env File (Recommended)

All scripts now automatically load environment variables from the `.env` file when run with the virtual environment:

```bash
# Activate the virtual environment (optional)
source .venv/bin/activate

# Run Dataverse backup
python dataverse_backup.py

# Run SharePoint incremental backup
python sharepoint_incremental_backup.py --type full  # First time
python sharepoint_incremental_backup.py              # Subsequent runs

# Run Exchange incremental backup
python exchange_incremental_backup.py --type full    # First time
python exchange_incremental_backup.py                # Subsequent runs
```

### Using UV with Unified .env File

```bash
# Run Dataverse backup
uv run dataverse_backup.py

# Run SharePoint incremental backup
uv run sharepoint_incremental_backup.py --type full  # First time
uv run sharepoint_incremental_backup.py              # Subsequent runs

# Run Exchange incremental backup
uv run exchange_incremental_backup.py --type full    # First time
uv run exchange_incremental_backup.py                # Subsequent runs
```

### Legacy Usage with Separate .env Files

For backward compatibility, you can still use separate `.env.*` files:

```bash
# Dataverse Backup
uv run --env-file .env.dataverse dataverse_backup.py

# SharePoint Incremental Backup
uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --type full
uv run --env-file .env.sharepoint sharepoint_incremental_backup.py

# Exchange/Outlook Incremental Backup
uv run --env-file .env.exchange exchange_incremental_backup.py --type full
uv run --env-file .env.exchange exchange_incremental_backup.py
```

### Common Commands

#### SharePoint Backup
```bash
# First time: Full backup to populate checksum database
python sharepoint_incremental_backup.py --type full

# Subsequent runs: Incremental backup (only changed files)
python sharepoint_incremental_backup.py

# View backup statistics
python sharepoint_incremental_backup.py --stats

# Cleanup old records (keep last 90 days)
python sharepoint_incremental_backup.py --cleanup 90
```

#### Exchange Backup
```bash
# First time: Full backup
python exchange_incremental_backup.py --type full

# Subsequent runs: Incremental backup
python exchange_incremental_backup.py

# View backup statistics
python exchange_incremental_backup.py --stats

# Cleanup old records (keep last 90 days)
python exchange_incremental_backup.py --cleanup 90

# Backup with specific options
python exchange_incremental_backup.py \
  --backup-dir backup/exchange \
  --max-emails 1000 \  # Optional: Limit to 1000 emails per user (0 = unlimited)
  --no-attachments \
  --format json
```

#### Dataverse Backup
```bash
# Run full Dataverse backup
python dataverse_backup.py
```

#### Database Rebuild Tool
```bash
# Rebuild both SharePoint and Exchange databases from existing backup files
python rebuild_databases.py

# Rebuild SharePoint database only
python rebuild_databases.py --type sharepoint

# Rebuild Exchange database only  
python rebuild_databases.py --type exchange

# Custom paths and dry-run mode
python rebuild_databases.py \
  --backup-dir /mnt/backup \
  --sharepoint-db /var/backup/sp.db \
  --exchange-db /var/backup/ex.db \
  --dry-run \
  --verbose
```

## Project Structure

```
.
├── ARCHIVE/                          # Archived scripts and documentation
├── backup/                           # Backup output directory
├── checksum_db.py                    # SharePoint checksum database
├── checksum_db_enhanced.py           # Enhanced checksum database with eTag/cTag support
├── dataverse_backup.py               # Dataverse backup script
├── dataverse_requirements.txt        # Dataverse-specific requirements
├── exchange_backup.py                # Exchange backup core module
├── exchange_checksum_db.py           # Exchange checksum database
├── exchange_incremental_backup.py    # Exchange incremental backup script
├── exchange_incremental_optimized.py # Optimized Exchange backup (10-100x faster)
├── OPTIMIZATION_README.md            # Performance optimization guide
├── PERFORMANCE_OPTIMIZATION.md       # SharePoint performance optimization details
├── rebuild_databases.py              # Database rebuild tool (offline reconstruction)
├── sharepoint_incremental_backup.py  # SharePoint incremental backup script
├── sharepoint_incremental_optimized.py # Optimized SharePoint backup (15-30x faster)
├── .env                              # Unified environment configuration (NEW)
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

#### Using Virtual Environment (Recommended)
```bash
# Edit crontab
crontab -e

# Add lines to run incremental backups daily at 2 AM
0 2 * * * cd /path/to/microsoft-365-backup-tools && .venv/bin/python sharepoint_incremental_backup.py
0 3 * * * cd /path/to/microsoft-365-backup-tools && .venv/bin/python exchange_incremental_backup.py
0 4 * * 0 cd /path/to/microsoft-365-backup-tools && .venv/bin/python dataverse_backup.py
```

#### Using UV
```bash
# Edit crontab
crontab -e

# Add lines to run incremental backups daily at 2 AM
0 2 * * * cd /path/to/microsoft-365-backup-tools && uv run sharepoint_incremental_backup.py
0 3 * * * cd /path/to/microsoft-365-backup-tools && uv run exchange_incremental_backup.py
0 4 * * 0 cd /path/to/microsoft-365-backup-tools && uv run dataverse_backup.py
```

### Windows (Task Scheduler)

#### Using Virtual Environment
```
cmd /c "cd C:\path\to\microsoft-365-backup-tools && .venv\Scripts\python.exe sharepoint_incremental_backup.py"
cmd /c "cd C:\path\to\microsoft-365-backup-tools && .venv\Scripts\python.exe exchange_incremental_backup.py"
cmd /c "cd C:\path\to\microsoft-365-backup-tools && .venv\Scripts\python.exe dataverse_backup.py"
```

#### Using UV
```
cmd /c "cd C:\path\to\microsoft-365-backup-tools && uv run sharepoint_incremental_backup.py"
cmd /c "cd C:\path\to\microsoft-365-backup-tools && uv run exchange_incremental_backup.py"
cmd /c "cd C:\path\to\microsoft-365-backup-tools && uv run dataverse_backup.py"
```

## Enhanced Logging with Loguru

All backup scripts now use the `loguru` library for enhanced logging with the following features:

### Logging Levels

The scripts use a custom hierarchy of logging levels for different types of messages:

- **TRACE** (🔍): Most detailed level - logs every file being processed, API calls, etc.
- **DEBUG** (🐛): Detailed debugging information - file checks, size comparisons, etc.
- **INFO** (ℹ️): Regular information - backup started, sites found, etc.
- **SUCCESS** (✅): Top-level success messages - authentication successful, backup completed
- **WARNING** (⚠️): Warnings - permission issues, missing files, etc.
- **ERROR** (❌): Errors - failed downloads, authentication errors, etc.
- **CRITICAL** (💥): Critical errors - system failures, etc.

### Log Output

- **Console**: Colored output with icons for easy readability (INFO level and above by default)
- **File**: Detailed logs to `*.log` files with TRACE level for complete debugging
- **Log Rotation**: Automatic rotation when logs reach 10 MB
- **Retention**: Logs kept for 30 days, compressed with zip

### Controlling Log Verbosity

By default, console output shows INFO level and above. To see more detailed logs:

```bash
# Run with environment variable to change log level
LOGURU_LEVEL=TRACE python sharepoint_incremental_backup.py --help

# Or modify the script to change the default level in logger.add()
```

### Example Log Output

```
2026-02-16 11:16:45 | INFO    | __main__:main:658 - Loaded environment variables from .env file
2026-02-16 11:16:45 | SUCCESS | __main__:_get_access_token:101 - Graph API authentication successful
2026-02-16 11:16:46 | TRACE   | __main__:_process_file:400 - Processing file 'document.docx' (size: 1048576 bytes)
2026-02-16 11:16:46 | DEBUG   | __main__:_process_file:420 - Skipped (unchanged): document.docx
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

4. **Logging Issues**:
   - Check that `loguru` is installed (`uv sync` to install dependencies)
   - Verify log file permissions in the working directory

5. **Token Expiration During Long Backups**:
   - Exchange backup now includes automatic token refresh
   - Tokens automatically refresh when older than 50 minutes (tokens expire in 60-90 minutes)
   - 401 errors trigger automatic token refresh and retry
   - Backups can now run indefinitely without token expiration issues

### Logs

Check log files for detailed information:
- `sharepoint_incremental_backup.log` - SharePoint backup logs (TRACE level)
- `exchange_incremental_backup.log` - Exchange backup logs (TRACE level)  
- `dataverse_backup.log` - Dataverse backup logs (TRACE level)

Log files include complete debugging information and are automatically rotated and compressed.

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