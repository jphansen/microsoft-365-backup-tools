# SharePoint Backup App Registration Guide

This guide walks you through creating an Azure AD (Entra ID) App Registration for the SharePoint backup script.

## Prerequisites

1. **Azure AD Administrator Access**: You need permissions to create app registrations in your Azure AD tenant
2. **SharePoint Site**: A SharePoint site you want to backup
3. **Global Administrator or Application Administrator role** (recommended)

## Step-by-Step Setup

### 1. Create App Registration

1. Go to the [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations** → **New registration**
3. Configure the app:
   - **Name**: `SharePoint Backup Tool` (or your preferred name)
   - **Supported account types**: 
     - For single tenant: `Accounts in this organizational directory only`
     - For multi-tenant: `Accounts in any organizational directory`
   - **Redirect URI**: Leave blank (we're using client credentials flow)
   - Click **Register**

### 2. Configure API Permissions

1. In your new app registration, go to **API permissions** → **Add a permission**
2. Select **Microsoft Graph** → **Application permissions**
3. Add the following permissions:
   - **Sites.Read.All** (Read items in all site collections)
   - **Sites.ReadWrite.All** (Read and write items in all site collections) - *Required for full backup*
   - **User.Read.All** (Read all users' full profiles) - *Optional, for user metadata*
   
   **Note**: Application permissions require admin consent.

4. Click **Grant admin consent for [Your Organization]** to grant the permissions

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

## References

- [Microsoft Graph Permissions Reference](https://docs.microsoft.com/en-us/graph/permissions-reference)
- [SharePoint REST API Documentation](https://docs.microsoft.com/en-us/sharepoint/dev/sp-add-ins/get-to-know-the-sharepoint-rest-service)
- [Office365 Python Client Documentation](https://github.com/vgrem/Office365-REST-Python-Client)