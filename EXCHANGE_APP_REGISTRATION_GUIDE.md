# Exchange/Outlook Backup - App Registration & Security Setup Guide

## Overview
This guide explains how to configure Azure AD App Registration for Exchange/Outlook backup using Microsoft Graph API.

## Prerequisites
- Azure AD tenant administrator access
- Existing Microsoft 365 Backup Tools setup
- Basic understanding of Azure AD App Registrations

## Step 1: Update Existing App Registration (Recommended)

If you already have the `HM-SharepointBackup` app registration, you can add Exchange permissions to it:

### 1.1 Navigate to Azure AD App Registration
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to: **Azure Active Directory** → **App registrations**
3. Find and select: **HM-SharepointBackup**

### 1.2 Add Exchange Mail Permissions
1. In the app registration, go to: **API permissions**
2. Click: **Add a permission**
3. Select: **Microsoft Graph**
4. Choose: **Application permissions** (not Delegated permissions)
5. Search for and select the following permissions:
   - **Mail.Read** - Read mail in all mailboxes
   - **Mail.ReadWrite** - Read and write mail in all mailboxes
   - **MailboxSettings.Read** - Read user mailbox settings
   - **User.Read.All** - Read all users' full profiles (if not already added)

6. Click: **Add permissions**

### 1.3 Grant Admin Consent
1. Click: **Grant admin consent for [Your Tenant Name]**
2. Confirm: **Yes**
3. Wait 10-15 minutes for permissions to propagate

## Step 2: Create New App Registration (Alternative)

If you prefer a separate app for Exchange backup:

### 2.1 Create New App Registration
1. Go to: **Azure Active Directory** → **App registrations** → **New registration**
2. Name: `HM-ExchangeBackup`
3. Supported account types: **Accounts in this organizational directory only**
4. Redirect URI: Leave blank (we're using client credentials)
5. Click: **Register**

### 2.2 Configure API Permissions
1. Go to: **API permissions**
2. Click: **Add a permission**
3. Select: **Microsoft Graph**
4. Choose: **Application permissions**
5. Add the following permissions:
   - **Mail.Read**
   - **Mail.ReadWrite** 
   - **MailboxSettings.Read**
   - **User.Read.All**

### 2.3 Create Client Secret
1. Go to: **Certificates & secrets**
2. Click: **New client secret**
3. Description: `Exchange Backup Secret`
4. Expires: **24 months** (recommended for backup applications)
5. Click: **Add**
6. **IMPORTANT**: Copy the secret value immediately (you won't see it again)

### 2.4 Note Application Details
- **Application (client) ID**: Copy this value
- **Directory (tenant) ID**: Copy this value
- **Client secret**: The value you just copied

## Step 3: Configure Environment Variables

### 3.1 Create `.env.exchange` File
```bash
cp .env.exchange.example .env.exchange
```

### 3.2 Edit `.env.exchange` with Your Values
```
# Exchange/Outlook Backup Configuration
EXCHANGE_TENANT_ID=your-tenant-id-here
EXCHANGE_CLIENT_ID=your-client-id-here
EXCHANGE_CLIENT_SECRET=your-client-secret-here

# Backup Settings
EXCHANGE_BACKUP_DIR=backup/exchange
EXCHANGE_USER_EMAIL=user@yourdomain.com  # Optional: Specific user to backup
EXCHANGE_INCLUDE_ATTACHMENTS=true
EXCHANGE_MAX_EMAILS_PER_BACKUP=1000
```

## Step 4: Required Permissions Explained

### Mail.Read
- **Purpose**: Read mail in all mailboxes
- **Scope**: Application permission (app-only)
- **What it allows**: Read emails, metadata, and folder structure
- **Security consideration**: Can read ALL emails in ALL mailboxes

### Mail.ReadWrite
- **Purpose**: Read and write access to mail
- **Scope**: Application permission
- **What it allows**: Read and modify emails (for marking as read/backed up)
- **Security consideration**: Can modify email content and status

### MailboxSettings.Read
- **Purpose**: Read mailbox settings
- **Scope**: Application permission
- **What it allows**: Read mailbox configuration, timezone, language settings
- **Security consideration**: Low risk, read-only access to settings

### User.Read.All
- **Purpose**: Read all users' profiles
- **Scope**: Application permission
- **What it allows**: List users in the tenant to backup their mailboxes
- **Security consideration**: Can read user directory information

## Step 5: Security Best Practices

### 5.1 Secret Management
- Store client secrets in `.env.exchange` file (never commit to git)
- Use Azure Key Vault for production deployments
- Rotate secrets every 6-12 months

### 5.2 Least Privilege Principle
- Start with only **Mail.Read** if you only need read access
- Add **Mail.ReadWrite** only if you need to mark emails as backed up
- Consider creating separate apps for different backup scenarios

### 5.3 Monitoring & Auditing
1. Enable Azure AD audit logs
2. Monitor Graph API usage in Azure Monitor
3. Set up alerts for unusual activity

### 5.4 Network Security
- Restrict app registration to specific IP ranges if possible
- Use Private Endpoints for Azure services
- Implement network security groups

## Step 6: Testing the Configuration

### 6.1 Test Environment Variables
```bash
uv run --env-file .env.exchange python test_exchange_env.py
```

### 6.2 Test Graph API Access
```bash
uv run --env-file .env.exchange python test_exchange_access.py
```

### 6.3 Run Test Backup
```bash
uv run --env-file .env.exchange python exchange_backup.py --dry-run
```

## Troubleshooting

### Common Issues

#### 1. "Insufficient privileges" error
- Ensure admin consent was granted
- Wait 10-15 minutes for propagation
- Check that Application permissions (not Delegated) were selected

#### 2. "Invalid client secret" error
- Verify the secret was copied correctly
- Check if the secret has expired
- Create a new client secret

#### 3. "User not found" error
- Ensure User.Read.All permission is granted
- Verify the user email exists in Azure AD
- Check if the app has access to the user's mailbox

#### 4. "Access denied" error
- Verify the app has Mail.Read permission
- Check if the user's mailbox is enabled
- Ensure the app registration is in the same tenant as the user

## Next Steps

After completing this setup:
1. Run a test backup to verify configuration
2. Schedule regular backups using cron or Task Scheduler
3. Monitor backup logs for any issues
4. Consider implementing incremental backup for efficiency

## Support

For issues with this setup:
1. Check Azure AD audit logs
2. Review Graph API documentation
3. Contact your Azure AD administrator
4. Check the project GitHub issues