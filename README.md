# Microsoft 365 Backup Tools

A collection of Python tools for backing up Microsoft 365 services including SharePoint sites and Dataverse databases.

## Tools Included

### 1. SharePoint Site Backup Tool
Backs up an entire SharePoint site from Office 365, including document libraries, lists, files, folders, and metadata.

### 2. Dataverse Database Backup Tool  
Backs up an entire Microsoft Dataverse (Power Platform) database with all data exported to JSON format.

## Quick Start

### SharePoint Backup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your SharePoint credentials

# Run backup
python sharepoint_backup.py
```

### Dataverse Backup
```bash
# Install dependencies  
pip install -r dataverse_requirements.txt

# Configure environment variables
cp .env.dataverse.example .env.dataverse
# Edit .env.dataverse with your Dataverse credentials

# Run backup
python dataverse_backup.py
```

## Detailed Documentation

- [SharePoint Backup Documentation](#features) - Complete guide for SharePoint backup tool (see below)
- [Dataverse Backup Documentation](DATAVERSE_README.md) - Complete guide for Dataverse backup tool

## Features

- ✅ Backs up all document libraries with files and folder structure
- ✅ Backs up all SharePoint lists with items
- ✅ Downloads file metadata (creation date, author, etc.)
- ✅ Preserves folder hierarchy
- ✅ Saves site metadata
- ✅ Comprehensive logging
- ✅ Timestamped backup folders

## Prerequisites

1. **Azure AD App Registration**
   - Register an application in Azure AD
   - Grant SharePoint permissions:
     - `Sites.Read.All` (Application permission)
     - Or `Sites.FullControl.All` for full access
   - Create a client secret
   - Grant admin consent for the permissions

2. **Python 3.7+**

## Installation

1. Install required packages:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```bash
export SHAREPOINT_SITE_URL="https://yourtenant.sharepoint.com/sites/yoursite"
export SHAREPOINT_CLIENT_ID="your-azure-ad-app-client-id"
export SHAREPOINT_CLIENT_SECRET="your-azure-ad-app-client-secret"
export BACKUP_DIR="backup"  # Optional, defaults to "backup"
```

## Usage

### Basic Usage

```bash
python sharepoint_backup.py
```

### Using Environment Variables

Create a `.env` file or export variables:

```bash
# Linux/Mac
export SHAREPOINT_SITE_URL="https://contoso.sharepoint.com/sites/ProjectSite"
export SHAREPOINT_CLIENT_ID="12345678-1234-1234-1234-123456789abc"
export SHAREPOINT_CLIENT_SECRET="your-secret-value"

python sharepoint_backup.py
```

```powershell
# Windows PowerShell
$env:SHAREPOINT_SITE_URL="https://contoso.sharepoint.com/sites/ProjectSite"
$env:SHAREPOINT_CLIENT_ID="12345678-1234-1234-1234-123456789abc"
$env:SHAREPOINT_CLIENT_SECRET="your-secret-value"

python sharepoint_backup.py
```

## Azure AD App Setup

### Step-by-Step Guide

1. **Go to Azure Portal** (https://portal.azure.com)

2. **Register a New Application**:
   - Navigate to "Azure Active Directory" > "App registrations"
   - Click "New registration"
   - Name: "SharePoint Backup Tool"
   - Supported account types: "Accounts in this organizational directory only"
   - Click "Register"

3. **Note the Application (client) ID**:
   - This is your `SHAREPOINT_CLIENT_ID`

4. **Create a Client Secret**:
   - Go to "Certificates & secrets"
   - Click "New client secret"
   - Description: "Backup Tool Secret"
   - Expiry: Choose appropriate duration
   - Click "Add"
   - **Copy the secret value immediately** (this is your `SHAREPOINT_CLIENT_SECRET`)

5. **Grant API Permissions**:
   - Go to "API permissions"
   - Click "Add a permission"
   - Choose "SharePoint"
   - Select "Application permissions"
   - Add `Sites.Read.All` or `Sites.FullControl.All`
   - Click "Add permissions"
   - **Click "Grant admin consent"** (requires admin privileges)

6. **Get your Site URL**:
   - Navigate to your SharePoint site in a browser
   - Copy the URL (e.g., `https://contoso.sharepoint.com/sites/YourSite`)
   - This is your `SHAREPOINT_SITE_URL`

## Backup Structure

The tool creates backups with the following structure:

```
backup/
└── sharepoint_backup_20231201_143022/
    ├── DocumentLibraries/
    │   ├── Documents/
    │   │   ├── file1.pdf
    │   │   ├── file1.pdf.metadata.json
    │   │   ├── Subfolder/
    │   │   │   ├── file2.docx
    │   │   │   └── file2.docx.metadata.json
    │   └── Shared Documents/
    │       └── ...
    ├── Lists/
    │   ├── Tasks.json
    │   ├── Announcements.json
    │   └── CustomList.json
    ├── site_metadata.json
    └── sharepoint_backup.log
```

## File Metadata

Each downloaded file includes a `.metadata.json` file containing:
- File name
- Server relative URL
- Creation time
- Last modified time
- File size
- Author information
- Modified by information

## Logging

The tool creates detailed logs:
- Console output for real-time monitoring
- `sharepoint_backup.log` file in the backup directory

## Troubleshooting

### Authentication Errors
- Verify your Client ID and Client Secret are correct
- Ensure admin consent was granted for API permissions
- Check that the app has appropriate SharePoint permissions

### Permission Errors
- The app needs `Sites.Read.All` or `Sites.FullControl.All` permissions
- Verify admin consent was granted

### Connection Errors
- Verify the site URL is correct and accessible
- Check your network connection
- Ensure the SharePoint site exists

## Security Notes

- **Never commit credentials to version control**
- Store credentials in environment variables or secure key vaults
- Use Azure Key Vault in production environments
- Regularly rotate client secrets
- Use least-privilege permissions (Sites.Read.All for backups)

## Limitations

- System folders (starting with `_`) are skipped
- Hidden lists are not backed up by default
- Large files may take time to download
- API throttling may occur with very large sites

## License

MIT License - Feel free to modify and use as needed.
