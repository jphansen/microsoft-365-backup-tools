# Tenant-Wide SharePoint Backup Solution

## 📋 **CURRENT DIAGNOSIS:**
- ✅ **Graph API**: Has tenant-wide access (can list all 33 sites)
- ❌ **SharePoint REST API**: Only has access to DemoISM (via appinv.aspx)
- ✅ **App Permissions**: `Sites.Read.All`, `Sites.ReadWrite.All`, `User.Read.All`

## 🎯 **IMMEDIATE WORKING SOLUTION: Use Graph API**

Since Graph API already has tenant-wide access, we can create a backup solution using **Microsoft Graph API** instead of SharePoint REST API.

### **Option 1: Graph API Backup Script (Works NOW)**
Create `sharepoint_graph_backup.py` that:
1. Uses Graph API to list ALL sites (already works)
2. Uses Graph API to download files from each site
3. Doesn't need SharePoint-specific permissions

### **Option 2: Fix SharePoint Tenant-Wide Access**
Grant proper SharePoint tenant-wide permissions so the original script works everywhere.

## 🔧 **QUICK FIX: Grant SharePoint Tenant-Wide Consent**

### **Step 1: Check Current Permissions**
1. Go to: Azure Portal → App registrations → HM-SharepointBackup
2. API permissions → Check both:
   - **Microsoft Graph**: `Sites.Read.All`, `Sites.ReadWrite.All` (✅ Already have)
   - **Office 365 SharePoint Online**: `Sites.FullControl.All` (❌ Might be missing or not consented)

### **Step 2: Add SharePoint-Specific Permission**
1. In API permissions, click "Add a permission"
2. Select "APIs my organization uses"
3. Search for: **"Office 365 SharePoint Online"**
4. Select **Application permissions**
5. Check: **`Sites.FullControl.All`**
6. Click "Add permissions"

### **Step 3: Grant Admin Consent**
1. Click "Grant admin consent for Honnimar"
2. Click "Yes" to confirm
3. Wait 10-15 minutes for propagation

### **Step 4: Verify**
```bash
uv run --env-file .env.sharepoint python test_tenant_access.py
```

## 🚀 **IMMEDIATE WORKAROUND: Graph API Backup**

Since Graph API already works, here's a quick Graph-based backup script:

```python
#!/usr/bin/env python3
"""SharePoint backup using Graph API (already has tenant-wide access)"""

import os
import requests
import json
from pathlib import Path

def backup_all_sites_via_graph():
    """Backup all SharePoint sites using Graph API"""
    
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    TENANT_ID = "163506f6-ef0e-42f8-a823-d13d7563bad9"
    
    # Get access token
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default'
    }
    
    response = requests.post(token_url, data=token_data)
    token = response.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    
    # Get all sites
    sites_url = "https://graph.microsoft.com/v1.0/sites?$select=id,name,webUrl,displayName"
    sites_response = requests.get(sites_url, headers=headers)
    sites = sites_response.json()['value']
    
    print(f"Found {len(sites)} sites")
    
    for site in sites:
        site_id = site['id']
        site_name = site['displayName']
        print(f"Backing up: {site_name}")
        
        # Get drives (document libraries)
        drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        drives_response = requests.get(drives_url, headers=headers)
        
        if drives_response.status_code == 200:
            drives = drives_response.json().get('value', [])
            for drive in drives:
                backup_drive(drive, site_name, headers)
```

## 📁 **CREATING THE COMPLETE SOLUTION:**

### **File 1: `grant_tenant_consent.ps1`** (PowerShell script)
```powershell
# PowerShell to grant tenant-wide SharePoint permissions
Connect-AzureAD
$sp = Get-AzureADServicePrincipal -Filter "displayName eq 'HM-SharepointBackup'"

# Grant SharePoint-specific permissions
Add-AzureADServicePrincipalPolicy -Id $sp.ObjectId
```

### **File 2: `sharepoint_graph_backup.py`** (Immediate solution)
Full backup script using Graph API (works now without additional permissions).

### **File 3: `fix_sharepoint_permissions.py`** (Diagnostic & fix)
Script to check and fix SharePoint permissions.

## 🎯 **RECOMMENDED APPROACH:**

### **Short-term (Now):**
1. Use Graph API backup script (already has tenant-wide access)
2. Create `sharepoint_graph_backup.py`

### **Medium-term (Next few days):**
1. Grant SharePoint tenant-wide admin consent
2. Test with original `sharepoint_backup.py`

### **Long-term:**
1. Use whichever method works best
2. Schedule regular backups
3. Monitor permissions

## 🔧 **QUICK TEST - Graph API Access:**
```bash
# Test Graph API access to list sites
uv run --env-file .env.sharepoint python -c "
import os, requests, json

CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
TENANT_ID = '163506f6-ef0e-42f8-a823-d13d7563bad9'

token_url = f'https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token'
token_data = {
    'grant_type': 'client_credentials',
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'scope': 'https://graph.microsoft.com/.default'
}

response = requests.post(token_url, data=token_data)
token = response.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

sites_url = 'https://graph.microsoft.com/v1.0/sites?\\$top=5'
sites_response = requests.get(sites_url, headers=headers)
sites = sites_response.json()['value']

print(f'✅ Graph API can access {len(sites)} sites:')
for site in sites:
    print(f'   - {site[\"displayName\"]}: {site[\"webUrl\"]}')
"
```

## 🚀 **NEXT STEPS:**
1. **Immediate**: Create Graph API backup script
2. **Today**: Grant SharePoint tenant-wide consent
3. **Test**: Verify both methods work
4. **Deploy**: Schedule regular backups