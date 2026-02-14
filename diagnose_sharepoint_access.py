#!/usr/bin/env python3
"""Diagnose SharePoint access issues with detailed troubleshooting"""

import os
import sys
import requests
import json
from datetime import datetime

def get_azure_token(client_id, client_secret, tenant_id):
    """Get Azure AD token for Microsoft Graph API"""
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': 'https://graph.microsoft.com/.default'
    }
    
    try:
        response = requests.post(token_url, data=token_data)
        response.raise_for_status()
        return response.json()['access_token']
    except Exception as e:
        print(f"❌ Failed to get Azure AD token: {str(e)}")
        if response.status_code == 401:
            print("   This usually means invalid client ID or secret")
        return None

def check_graph_api_permissions(token):
    """Check what permissions the app has via Microsoft Graph API"""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    try:
        # Try to get site info via Graph API
        site_url = "https://graph.microsoft.com/v1.0/sites/honnimar.sharepoint.com:/sites/DemoISM"
        response = requests.get(site_url, headers=headers)
        
        if response.status_code == 200:
            site_data = response.json()
            print(f"✅ Can access site via Graph API: {site_data.get('webUrl')}")
            print(f"   Site ID: {site_data.get('id')}")
            return True
        else:
            print(f"❌ Cannot access site via Graph API: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Graph API check failed: {str(e)}")
        return False

def check_app_permissions_in_portal():
    """Provide instructions to check app permissions in Azure Portal"""
    print("\n" + "="*80)
    print("CHECK APP PERMISSIONS IN AZURE PORTAL")
    print("="*80)
    
    print("1. Go to Azure Portal → Azure Active Directory → App registrations")
    print("2. Find your app 'HM-SharepointBackup'")
    print("3. Go to 'API permissions' section")
    print("4. Verify you have:")
    print("   - Microsoft Graph → Sites.ReadWrite.All (Application permission)")
    print("   - Status should show '✓ Granted for [Your Organization]'")
    print("5. If not granted, click 'Grant admin consent'")
    print("\nNOTE: After granting permissions, wait 5-10 minutes for propagation")

def check_sharepoint_site_permissions():
    """Provide instructions to check SharePoint site permissions"""
    print("\n" + "="*80)
    print("CHECK SHAREPOINT SITE PERMISSIONS")
    print("="*80)
    
    print("1. Go to your SharePoint site: https://honnimar.sharepoint.com/sites/DemoISM")
    print("2. Click gear icon → 'Site permissions'")
    print("3. Click 'Advanced permissions settings'")
    print("4. Check if your app is listed:")
    print("   - Look for: appid@tenantid")
    print("   - Example: 3b1a7c1f-fbf2-4455-9e85-87f42a4e1ef3@163506f6-ef0e-42f8-a823-d13d7563bad9")
    print("5. If not present, grant permissions:")
    print("   - Click 'Grant permissions'")
    print("   - Enter: 3b1a7c1f-fbf2-4455-9e85-87f42a4e1ef3@163506f6-ef0e-42f8-a823-d13d7563bad9")
    print("   - Select 'Full Control'")
    print("   - Click 'Share'")

def test_direct_sharepoint_auth():
    """Test direct SharePoint authentication with more details"""
    from office365.runtime.auth.client_credential import ClientCredential
    from office365.sharepoint.client_context import ClientContext
    
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    TENANT_ID = "163506f6-ef0e-42f8-a823-d13d7563bad9"  # From your .env file
    
    print("\n" + "="*80)
    print("DIRECT SHAREPOINT AUTHENTICATION TEST")
    print("="*80)
    
    try:
        print("🔑 Creating credentials...")
        credentials = ClientCredential(CLIENT_ID, CLIENT_SECRET)
        
        print("🔗 Creating client context...")
        ctx = ClientContext(SITE_URL).with_credentials(credentials)
        
        print("📡 Testing basic site access...")
        
        # Try a simpler query first
        print("   Trying to get site title...")
        web = ctx.web
        ctx.load(web, ["Title", "Url"])
        ctx.execute_query()
        
        print(f"✅ SUCCESS! Connected to: {web.properties['Title']}")
        print(f"   Site URL: {web.properties['Url']}")
        return True
        
    except Exception as e:
        print(f"❌ Failed: {str(e)}")
        
        # More specific error analysis
        error_str = str(e).lower()
        
        if "forbidden" in error_str:
            print("\n🔍 FORBIDDEN ERROR ANALYSIS:")
            print("   The app can authenticate but doesn't have permission.")
            print("   Most likely causes:")
            print("   1. Missing 'Sites.ReadWrite.All' permission in Azure AD")
            print("   2. App not granted access to this specific SharePoint site")
            print("   3. Permissions haven't propagated yet (wait 5-10 min)")
            
        elif "unauthorized" in error_str:
            print("\n🔍 UNAUTHORIZED ERROR ANALYSIS:")
            print("   Authentication failed.")
            print("   Check client ID and secret are correct.")
            
        elif "not found" in error_str:
            print("\n🔍 NOT FOUND ERROR ANALYSIS:")
            print("   Site URL might be incorrect.")
            print("   Verify: https://honnimar.sharepoint.com/sites/DemoISM")
            
        return False

def main():
    print("🔍 SharePoint Access Diagnostics")
    print("="*80)
    
    # Load environment
    if not os.path.exists('.env.sharepoint'):
        print("❌ .env.sharepoint not found")
        return
    
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    TENANT_ID = "163506f6-ef0e-42f8-a823-d13d7563bad9"
    
    print(f"📋 Configuration:")
    print(f"   Site: {SITE_URL}")
    print(f"   Client ID: {CLIENT_ID[:8]}...")
    print(f"   Tenant ID: {TENANT_ID}")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    
    # Test 1: Get Azure AD token
    print("\n1. Testing Azure AD authentication...")
    token = get_azure_token(CLIENT_ID, CLIENT_SECRET, TENANT_ID)
    if token:
        print("✅ Azure AD authentication successful")
        
        # Test 2: Check Graph API permissions
        print("\n2. Testing Microsoft Graph API access...")
        graph_access = check_graph_api_permissions(token)
        if not graph_access:
            print("⚠️  Graph API access failed - checking permissions...")
            check_app_permissions_in_portal()
    else:
        print("❌ Azure AD authentication failed")
        print("   Check client ID and secret in Azure Portal")
    
    # Test 3: Direct SharePoint test
    print("\n3. Testing direct SharePoint access...")
    sharepoint_access = test_direct_sharepoint_auth()
    if not sharepoint_access:
        check_sharepoint_site_permissions()
    
    # Summary
    print("\n" + "="*80)
    print("DIAGNOSTIC SUMMARY")
    print("="*80)
    
    if token and sharepoint_access:
        print("✅ All tests passed! Your app should work.")
        print("\nNext: Run the backup script:")
        print("   uv run --env-file .env.sharepoint sharepoint_backup.py")
    else:
        print("⚠️  Issues detected. Follow the instructions above to fix.")
        print("\nMost common fix:")
        print("1. Go to Azure Portal → App registrations → HM-SharepointBackup")
        print("2. API permissions → Add 'Sites.ReadWrite.All' (Microsoft Graph)")
        print("3. Grant admin consent")
        print("4. Wait 10 minutes")
        print("5. Run this diagnostic again")

if __name__ == "__main__":
    main()