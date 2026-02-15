# Microsoft 365 Backup Tools - App Registration Guide

This guide walks you through creating and configuring Azure AD (Entra ID) App Registrations for SharePoint and Exchange/Outlook backup.

## Prerequisites

1. **Azure AD Administrator Access**: You need permissions to create app registrations in your Azure AD tenant
2. **SharePoint Site**: A SharePoint site you want to backup
3. **Global Administrator or Application Administrator role** (recommended)

## App Registration Options

### Option 1: Single App for Both SharePoint and Exchange (Recommended)
Create one app registration that has permissions for both SharePoint and Exchange backup.

### Option 2: Separate Apps for SharePoint and Exchange
Create separate app registrations if you want to isolate permissions or have different security requirements.

## Step-by-Step Setup for Combined App

### 1. Create App Registration

1. Go to the [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations** → **New registration**
3. Configure the app:
   - **Name**: `Microsoft 365 Backup Tools` (or your preferred name)
   - **Supported account types**: 
     - For single tenant: `Accounts in this organizational directory only`
     - For multi-tenant: `Accounts in any organizational directory`
   - **Redirect URI**: Leave blank (we're using client credentials flow)
   - Click **Register**

### 2. Configure API Permissions for Combined App

#### SharePoint Permissions:
1. In your new app registration, go to **API permissions** → **Add a permission**
2. Select **Microsoft Graph** → **Application permissions**
3. Add the following SharePoint permissions:
   - **Sites.Read.All** (Read items in all site collections)
   - **Sites.ReadWrite.All** (Read and write items in all site collections) - *Required for full backup*
   - **User.Read.All** (Read all users' full profiles) - *Required for Exchange backup and user metadata*

#### Exchange/Outlook Permissions:
4. Click **Add a permission** again
5. Select **Microsoft Graph** → **Application permissions**
6. Add the following Exchange permissions:
   - **Mail.Read** (Read mail in all mailboxes) - *Required for email backup*
   - **Mail.ReadWrite** (Read and write mail in all mailboxes) - *Optional, for marking emails as backed up*
   - **MailboxSettings.Read** (Read mailbox settings) - *Optional, for mailbox configuration*

**Note**: Application permissions require admin consent.

7. Click **Grant admin consent for [Your Organization]** to grant all permissions

### 3. Create Client Secret

1. In your app registration, go to **Certificates & secrets** → **Client secrets** → **New client secret**
2. Configure:
   - **Description**: `SharePoint Backup Secret`
   - **Expires**: Choose an appropriate duration (6 months, 1 year, or never)
3. Click **Add**
4. **IMPORTANT**: Copy the **Secret Value** immediately (you won't be able to see it again)
   - Save it in a secure location
   - You'll need this for your `.env.sharepoint` file

### 4. Get Application (Client) ID and Tenant ID

1. In your app registration overview, copy:
   - **Application (client) ID** - This is your `SHAREPOINT_CLIENT_ID`
   - **Directory (tenant) ID** - This is your `SHAREPOINT_TENANT_ID` (optional for the script)

### 5. Configure SharePoint Site Permissions

The app registration needs access to your specific SharePoint site:

#### Option A: Grant Access to All Sites (Simplest)
- The `Sites.ReadWrite.All` permission already grants access to all SharePoint sites in your tenant

#### Option B: Grant Access to Specific Site (More Secure)
1. Go to your SharePoint site
2. Click the gear icon → **Site permissions**
3. Click **Advanced permissions settings**
4. Click **Grant permissions**
5. Enter your app's client ID in the format: `appid@tenantid`
   - Example: `abcd1234-5678-90ef-ghij-klmnopqrstuv@yourtenant.onmicrosoft.com`
6. Select appropriate permissions (e.g., **Full Control** for backup)
7. Click **Share**

### 6. Update Environment File

Update your `.env.sharepoint` file with the actual values:

```bash
# SharePoint Site URL
SHAREPOINT_SITE_URL=https://your-tenant.sharepoint.com/sites/your-site

# Azure AD App Registration
SHAREPOINT_CLIENT_ID=your-application-client-id
SHAREPOINT_CLIENT_SECRET=your-client-secret-value

# Backup Configuration
BACKUP_DIR=backup/sharepoint
```

## Testing the Setup

### 1. Test Authentication

Create a simple test script to verify authentication works:

```python
#!/usr/bin/env python3
"""Test SharePoint authentication"""

import os
from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext

# Load from environment
SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')

print(f"Testing authentication to: {SITE_URL}")

try:
    credentials = ClientCredential(CLIENT_ID, CLIENT_SECRET)
    ctx = ClientContext(SITE_URL).with_credentials(credentials)
    
    # Try to get site info
    web = ctx.web
    ctx.load(web)
    ctx.execute_query()
    
    print(f"✅ Success! Connected to site: {web.properties['Title']}")
    print(f"   Site URL: {web.properties['Url']}")
    
except Exception as e:
    print(f"❌ Authentication failed: {str(e)}")
    print("\nTroubleshooting tips:")
    print("1. Verify CLIENT_ID and CLIENT_SECRET are correct")
    print("2. Check if client secret has expired")
    print("3. Verify app has required API permissions (Sites.ReadWrite.All)")
    print("4. Check if app has access to the specific SharePoint site")
```

Run the test:
```bash
uv run --env-file .env.sharepoint python test_auth.py
```

### 2. Test Backup Script

Once authentication works, test the full backup:
```bash
uv run --env-file .env.sharepoint sharepoint_backup.py
```

## Troubleshooting Common Issues

### 1. "Access Denied" or "Unauthorized" Errors
- **Cause**: Missing or insufficient permissions
- **Solution**: 
  - Verify `Sites.ReadWrite.All` permission is granted with admin consent
  - Check if app has access to the specific SharePoint site
  - Wait 5-10 minutes after granting permissions (propagation delay)

### 2. "Invalid client secret" Error
- **Cause**: Client secret expired or incorrect
- **Solution**: Create a new client secret and update `.env.sharepoint`

### 3. "Resource not found" Error
- **Cause**: Incorrect SharePoint site URL
- **Solution**: Verify the `SHAREPOINT_SITE_URL` is correct and accessible

### 4. "Insufficient privileges" Error
- **Cause**: App doesn't have write permissions
- **Solution**: Ensure `Sites.ReadWrite.All` is granted (not just `Sites.Read.All`)

## Security Best Practices

1. **Client Secret Management**:
   - Store secrets securely (use Azure Key Vault in production)
   - Set appropriate expiration dates
   - Rotate secrets regularly

2. **Permission Principle**:
   - Use least-privilege permissions
   - Grant access to specific sites instead of all sites when possible
   - Regularly review and audit app permissions

3. **Monitoring**:
   - Enable Azure AD audit logs
   - Monitor backup script execution
   - Set up alerts for failed authentication attempts

## Advanced Configuration

### Multi-Tenant Setup
If backing up from multiple tenants:
1. Set "Supported account types" to "Accounts in any organizational directory"
2. Each tenant admin must grant consent
3. Use different environment files for each tenant

### Service Principal Configuration
For production use, consider:
1. Creating a dedicated service principal
2. Using managed identities (if running in Azure)
3. Implementing certificate-based authentication instead of client secrets

## Next Steps

After successful app registration:
1. Test with a small site first
2. Monitor backup performance and logs
3. Set up automated backups using cron or Azure Functions
4. Implement error handling and notifications
5. Consider incremental backup strategies for large sites

## Exchange/Outlook Backup Configuration

### Environment Configuration for Exchange

Create a separate environment file for Exchange backup:

```bash
cp .env.exchange.example .env.exchange
```

Edit `.env.exchange` with your values:
```
# Exchange/Outlook Backup Configuration
EXCHANGE_TENANT_ID=your-tenant-id-here
EXCHANGE_CLIENT_ID=your-client-id-here  # Same as SHAREPOINT_CLIENT_ID if using combined app
EXCHANGE_CLIENT_SECRET=your-client-secret-here  # Same as SHAREPOINT_CLIENT_SECRET if using combined app

# Backup Settings
EXCHANGE_BACKUP_DIR=backup/exchange
EXCHANGE_USER_EMAIL=user@yourdomain.com  # Optional: Specific user to backup
EXCHANGE_INCLUDE_ATTACHMENTS=true
EXCHANGE_MAX_EMAILS_PER_BACKUP=1000
EXCHANGE_SKIP_ALREADY_READ=false
```

### Testing Exchange Backup

#### 1. Test Exchange Authentication
```bash
uv run --env-file .env.exchange python test_exchange_auth.py
```

#### 2. Test Exchange Backup Script
```bash
uv run --env-file .env.exchange python exchange_backup.py --dry-run
```

#### 3. Run Full Exchange Backup
```bash
uv run --env-file .env.exchange python exchange_backup.py
```

### Exchange-Specific Troubleshooting

#### 1. "Mailbox not enabled for this user" error
- **Cause**: User doesn't have an Exchange Online license
- **Solution**: Assign Exchange Online license to the user

#### 2. "Access denied to mailbox" error
- **Cause**: App doesn't have Mail.Read permission
- **Solution**: Verify Mail.Read permission is granted with admin consent

#### 3. "Too many requests" error
- **Cause**: Graph API rate limiting
- **Solution**: Implement throttling in backup script, use batch requests

#### 4. "Attachment too large" error
- **Cause**: Graph API has attachment size limits (typically 4MB)
- **Solution**: Large attachments are skipped by default, can be configured

## Security Considerations for Exchange Backup

### 1. Mail.Read vs Mail.ReadWrite
- **Mail.Read**: Read-only access to all mailboxes (recommended for backup)
- **Mail.ReadWrite**: Read and write access (can modify emails)
- **Recommendation**: Use Mail.Read unless you need to mark emails as backed up

### 2. User.Read.All Requirement
- Required to list users in the tenant
- Required to access user mailboxes via Graph API
- Consider creating a security group and limiting access if possible

### 3. Data Sensitivity
- Email backups contain sensitive information
- Encrypt backup files at rest
- Secure backup storage location
- Implement access controls for backup files

### 4. Compliance Considerations
- Check organizational policies for email backup
- Ensure backup retention aligns with data retention policies
- Consider legal and regulatory requirements (GDPR, HIPAA, etc.)

## Combined Backup Strategy

### Using Same App for Both Services
- **Advantages**: Single app to manage, simplified secret management
- **Disadvantages**: Broader permissions scope if compromised

### Backup Scheduling Example
```bash
# Daily SharePoint backup at 2 AM
0 2 * * * cd /path/to/microsoft-365-backup-tools && uv run --env-file .env.sharepoint sharepoint_backup.py

# Daily Exchange backup at 3 AM  
0 3 * * * cd /path/to/microsoft-365-backup-tools && uv run --env-file .env.exchange exchange_backup.py

# Weekly full backup on Sundays
0 4 * * 0 cd /path/to/microsoft-365-backup-tools && uv run --env-file .env.sharepoint sharepoint_backup.py --full
0 5 * * 0 cd /path/to/microsoft-365-backup-tools && uv run --env-file .env.exchange exchange_backup.py --full
```

## References

- [Microsoft Graph Permissions Reference](https://docs.microsoft.com/en-us/graph/permissions-reference)
- [Microsoft Graph Mail API Documentation](https://docs.microsoft.com/en-us/graph/api/resources/mail-api-overview)
- [SharePoint REST API Documentation](https://docs.microsoft.com/en-us/sharepoint/dev/sp-add-ins/get-to-know-the-sharepoint-rest-service)
- [Office365 Python Client Documentation](https://github.com/vgrem/Office365-REST-Python-Client)
- [Graph API Best Practices](https://docs.microsoft.com/en-us/graph/best-practices-concept)
