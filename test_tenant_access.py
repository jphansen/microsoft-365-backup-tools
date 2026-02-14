#!/usr/bin/env python3
"""Test tenant-wide SharePoint access"""

import os
from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext
import requests
import json

def test_tenant_wide_access():
    """Test if app has tenant-wide SharePoint access"""
    
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    TENANT_ID = "163506f6-ef0e-42f8-a823-d13d7563bad9"
    
    print("🔧 TESTING TENANT-WIDE SHAREPOINT ACCESS")
    print("="*80)
    
    # Test 1: Check if we can get access token
    print("1. Testing Azure AD Authentication...")
    try:
        token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
        token_data = {
            'grant_type': 'client_credentials',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'scope': 'https://graph.microsoft.com/.default'
        }
        
        response = requests.post(token_url, data=token_data)
        if response.status_code == 200:
            token = response.json()['access_token']
            print("   ✅ Azure AD authentication successful")
            
            # Decode token to check permissions
            import base64
            parts = token.split('.')
            if len(parts) > 1:
                payload = parts[1]
                padded = payload + '=' * (4 - len(payload) % 4)
                decoded = base64.b64decode(padded).decode('utf-8')
                claims = json.loads(decoded)
                
                print("   📋 Token claims:")
                print(f"      App ID: {claims.get('appid')}")
                print(f"      Tenant: {claims.get('tid')}")
                print(f"      Roles: {claims.get('roles', [])}")
        else:
            print(f"   ❌ Azure AD auth failed: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)[:100]}")
    
    # Test 2: Try accessing different SharePoint sites
    print("\n2. Testing SharePoint Site Access...")
    
    test_sites = [
        "https://honnimar.sharepoint.com/sites/DemoISM",  # Already working
        "https://honnimar.sharepoint.com",  # Root site
        "https://honnimar.sharepoint.com/sites",  # Sites collection
    ]
    
    for site_url in test_sites:
        print(f"\n   Testing: {site_url}")
        try:
            credentials = ClientCredential(CLIENT_ID, CLIENT_SECRET)
            ctx = ClientContext(site_url).with_credentials(credentials)
            
            web = ctx.web
            ctx.load(web, ["Title", "Url"])
            ctx.execute_query()
            
            print(f"      ✅ Access granted: {web.properties.get('Title', 'Unknown')}")
            
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg or "Access is denied" in error_msg:
                print(f"      ❌ 403 Forbidden - No tenant-wide access")
                print(f"      ℹ️  Need to grant tenant-wide admin consent")
            else:
                print(f"      ⚠️  Error: {error_msg[:80]}")
    
    # Test 3: Check Graph API for tenant-wide permissions
    print("\n3. Testing Microsoft Graph API Access...")
    try:
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        # Try to list sites - this requires tenant-wide permissions
        graph_url = "https://graph.microsoft.com/v1.0/sites?$select=webUrl,name"
        response = requests.get(graph_url, headers=headers)
        
        if response.status_code == 200:
            sites_data = response.json()
            print(f"   ✅ Graph API access successful!")
            print(f"   📁 Found {len(sites_data.get('value', []))} sites in tenant")
            
            # List first few sites
            for i, site in enumerate(sites_data.get('value', [])[:3]):
                print(f"      {i+1}. {site.get('name')} - {site.get('webUrl')}")
                
            if len(sites_data.get('value', [])) > 3:
                print(f"      ... and {len(sites_data.get('value', [])) - 3} more sites")
                
        elif response.status_code == 403:
            print("   ❌ Graph API 403 - No tenant-wide permissions")
            print("   ℹ️  App needs 'Sites.Read.All' or 'Sites.ReadWrite.All' permission")
        else:
            print(f"   ⚠️  Graph API returned: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Graph API test failed: {str(e)[:100]}")
    
    print("\n" + "="*80)
    print("🎯 DIAGNOSIS RESULTS:")
    print("="*80)
    
    print("If Test 2 fails for sites other than DemoISM:")
    print("1. ❌ App does NOT have tenant-wide SharePoint permissions")
    print("2. ℹ️  Only has access to sites explicitly granted via appinv.aspx")
    
    print("\nIf Test 3 (Graph API) succeeds:")
    print("1. ✅ App has tenant-wide Graph API permissions")
    print("2. ℹ️  But might still need SharePoint-specific configuration")
    
    print("\n" + "="*80)
    print("🔧 FIX FOR TENANT-WIDE ACCESS:")
    print("="*80)
    
    print("OPTION A: Grant Admin Consent (Recommended)")
    print("1. Azure Portal → App registrations → HM-SharepointBackup")
    print("2. API permissions → Microsoft Graph")
    print("3. Click 'Grant admin consent for Honnimar'")
    print("4. Click 'Yes' to confirm")
    print("5. Wait 10 minutes")
    
    print("\nOPTION B: Use SharePoint Admin Center")
    print("1. Go to: https://honnimar-admin.sharepoint.com")
    print("2. Advanced → API access")
    print("3. Find 'HM-SharepointBackup'")
    print("4. Click 'Approve' for tenant-wide access")
    
    print("\nOPTION C: PowerShell (Admin Required)")
    print("```powershell")
    print("# Run in Windows PowerShell with AzureAD module")
    print("Connect-AzureAD")
    print("$sp = Get-AzureADServicePrincipal -Filter \"displayName eq 'HM-SharepointBackup'\"")
    print("# Grant tenant-wide consent")
    print("New-AzureADServiceAppRoleAssignment -ObjectId $sp.ObjectId \\")
    print("  -PrincipalId $sp.ObjectId -ResourceId $sp.ObjectId -Id [guid]::Empty")
    print("```")
    
    print("\n" + "="*80)
    print("🧪 TEST AFTER FIX:")
    print("="*80)
    print("Run this test again after granting tenant-wide consent:")
    print("uv run --env-file .env.sharepoint python test_tenant_access.py")

if __name__ == "__main__":
    test_tenant_wide_access()