#!/usr/bin/env python3
"""Check current app permissions configuration and provide exact steps"""

import os
import requests
import json

def check_current_permissions():
    """Check what permissions the app currently has"""
    
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    TENANT_ID = "163506f6-ef0e-42f8-a823-d13d7563bad9"
    
    print("🔍 Checking Current App Permissions")
    print("="*80)
    
    # Get token for Microsoft Graph
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default'
    }
    
    try:
        response = requests.post(token_url, data=token_data)
        response.raise_for_status()
        token = response.json()['access_token']
        
        # Get service principal info
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Get app's service principal
        sp_url = f"https://graph.microsoft.com/v1.0/servicePrincipals?$filter=appId eq '{CLIENT_ID}'"
        sp_response = requests.get(sp_url, headers=headers)
        
        if sp_response.status_code == 200:
            sp_data = sp_response.json()
            if sp_data['value']:
                sp_id = sp_data['value'][0]['id']
                print(f"✅ Found service principal: {sp_id}")
                
                # Get app role assignments
                roles_url = f"https://graph.microsoft.com/v1.0/servicePrincipals/{sp_id}/appRoleAssignments"
                roles_response = requests.get(roles_url, headers=headers)
                
                if roles_response.status_code == 200:
                    roles = roles_response.json()
                    print(f"\n📋 Current App Role Assignments ({len(roles['value'])}):")
                    
                    if not roles['value']:
                        print("   ❌ No app role assignments found!")
                        print("   This explains the 403 error - app has no permissions")
                    else:
                        for role in roles['value']:
                            print(f"   • {role.get('appRoleId')} - {role.get('resourceDisplayName')}")
                
                # Check for SharePoint-specific permissions
                print("\n🔎 Checking for SharePoint-specific permissions...")
                
                # Try to get SharePoint site via Graph (this should work)
                site_url = "https://graph.microsoft.com/v1.0/sites/honnimar.sharepoint.com:/sites/DemoISM"
                site_response = requests.get(site_url, headers=headers)
                
                if site_response.status_code == 200:
                    print("   ✅ Has Microsoft Graph Sites.ReadWrite.All permission")
                else:
                    print(f"   ❌ Graph API access failed: {site_response.status_code}")
                
                # Provide exact Azure Portal steps
                print("\n" + "="*80)
                print("EXACT STEPS TO FIX IN AZURE PORTAL")
                print("="*80)
                
                print("1. Go to: https://portal.azure.com/#view/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/~/RegisteredApps")
                print("2. Click on: HM-SharepointBackup")
                print("3. In left menu, click: API permissions")
                print("4. Click: Add a permission")
                print("5. Click: APIs my organization uses")
                print("6. Search for: Office 365 SharePoint Online")
                print("7. Click on it")
                print("8. Select: Application permissions")
                print("9. Check: Sites.FullControl.All")
                print("10. Click: Add permissions")
                print("11. Click: Grant admin consent for HonniMar")
                print("12. Click: Yes")
                print("13. Wait 10 minutes")
                
                print("\n" + "="*80)
                print("ALTERNATIVE: Grant Direct Site Access")
                print("="*80)
                print("If API permissions don't work, try direct site access:")
                print("1. Go to: https://honnimar.sharepoint.com/sites/DemoISM/_layouts/15/user.aspx")
                print("2. Click: Grant Permissions")
                print("3. Enter: 3b1a7c1f-fbf2-4455-9e85-87f42a4e1ef3@163506f6-ef0e-42f8-a823-d13d7563bad9")
                print("4. Select: Full Control")
                print("5. Uncheck: Send email")
                print("6. Click: Share")
                
            else:
                print("❌ Service principal not found")
                print("   The app registration might not be properly configured")
        else:
            print(f"❌ Could not get service principal: {sp_response.status_code}")
            
    except Exception as e:
        print(f"❌ Error checking permissions: {str(e)}")
    
    print("\n" + "="*80)
    print("IMMEDIATE TEST")
    print("="*80)
    print("After making changes, test immediately with:")
    print("  uv run --env-file .env.sharepoint python quick_sharepoint_test.py")
    
    print("\n" + "="*80)
    print("COMMON MISTAKES TO CHECK")
    print("="*80)
    print("1. ✅ Client ID and Secret are correct (they are)")
    print("2. ❓ 'Office 365 SharePoint Online' API permission added")
    print("3. ❓ 'Sites.FullControl.All' selected (Application permission)")
    print("4. ❓ Admin consent granted (green checkmark)")
    print("5. ❓ Waited 10+ minutes after granting")
    print("6. ❓ Site URL is correct: https://honnimar.sharepoint.com/sites/DemoISM")

def main():
    check_current_permissions()

if __name__ == "__main__":
    main()