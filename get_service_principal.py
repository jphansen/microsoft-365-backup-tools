#!/usr/bin/env python3
"""Get the Service Principal Object ID for the app"""

import os
import requests
import json

def get_service_principal_info():
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    TENANT_ID = "163506f6-ef0e-42f8-a823-d13d7563bad9"
    
    print("🔍 Getting Service Principal Information")
    print("="*80)
    
    # Get token
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
        
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        # Get service principal details
        sp_url = f"https://graph.microsoft.com/v1.0/servicePrincipals?$filter=appId eq '{CLIENT_ID}'&$select=id,appId,displayName,appDisplayName"
        sp_response = requests.get(sp_url, headers=headers)
        
        if sp_response.status_code == 200:
            sp_data = sp_response.json()
            if sp_data['value']:
                sp = sp_data['value'][0]
                
                print("✅ Found Service Principal:")
                print(f"   Display Name: {sp.get('displayName')}")
                print(f"   App Display Name: {sp.get('appDisplayName')}")
                print(f"   App ID (Client ID): {sp.get('appId')}")
                print(f"   Object ID: {sp.get('id')}")
                print(f"   Tenant ID: {TENANT_ID}")
                
                print("\n" + "="*80)
                print("📋 CORRECT VALUES TO USE:")
                print("="*80)
                
                print("1. For SharePoint 'Grant Permissions':")
                print(f"   Try this format: i:0#.f|membership|{sp.get('appId')}@{TENANT_ID}")
                print(f"   OR: {sp.get('appId')}@{TENANT_ID}")
                print(f"   OR just the Object ID: {sp.get('id')}")
                
                print("\n2. For PowerShell PnP:")
                print(f"   -AppId {sp.get('id')}  # Use Object ID, not App ID")
                
                print("\n3. Alternative formats to try:")
                print(f"   a) {sp.get('appId')}")
                print(f"   b) {sp.get('id')}")
                print(f"   c) appid@{TENANT_ID}")
                print(f"   d) {sp.get('displayName')}")
                
                return sp.get('id'), sp.get('appId')
            else:
                print("❌ No service principal found")
                print("   The app registration might not be fully provisioned")
        else:
            print(f"❌ Could not get service principal: {sp_response.status_code}")
            print(f"   Response: {sp_response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    return None, None

def provide_exact_steps(object_id, app_id):
    """Provide exact steps based on the service principal info"""
    
    print("\n" + "="*80)
    print("🎯 EXACT STEPS TO GRANT SHAREPOINT ACCESS")
    print("="*80)
    
    print("METHOD A: SharePoint Admin Center (Recommended)")
    print("1. Go to: https://honnimar-admin.sharepoint.com")
    print("2. Sites → Active sites → Find 'DemoISM'")
    print("3. Click on it → Permissions tab")
    print("4. Click 'Add members'")
    print(f"5. Enter: {app_id}@{TENANT_ID}")
    print("6. Select 'Full Control'")
    print("7. Click 'Add'")
    
    print("\nMETHOD B: Graph API (Advanced)")
    print("1. Use this Graph API call:")
    print(f"   POST https://graph.microsoft.com/v1.0/sites/honnimar.sharepoint.com,sites/DemoISM/permissions")
    print("   Body: {")
    print(f'     "roles": ["write"],')
    print(f'     "grantedToIdentities": [{{"application": {{"id": "{object_id}"}}}}]')
    print("   }")
    
    print("\nMETHOD C: Manual Workaround")
    print("1. Create a test user in Azure AD")
    print("2. Grant that user access to SharePoint site")
    print("3. Use user credentials instead of app credentials")
    print("4. Update sharepoint_backup.py to use user auth")
    
    print("\n" + "="*80)
    print("⚠️  TROUBLESHOOTING TIPS:")
    print("="*80)
    print("1. The site might be a 'Private' channel in Teams")
    print("2. Try accessing the site first with your user account")
    print("3. Check if site exists: https://honnimar.sharepoint.com/sites/DemoISM")
    print("4. Verify you have admin rights to the site")

if __name__ == "__main__":
    TENANT_ID = "163506f6-ef0e-42f8-a823-d13d7563bad9"
    object_id, app_id = get_service_principal_info()
    
    if object_id and app_id:
        provide_exact_steps(object_id, app_id)
    
    print("\n" + "="*80)
    print("QUICK TEST COMMAND:")
    print("="*80)
    print("After granting access, test with:")
    print("  uv run --env-file .env.sharepoint python quick_sharepoint_test.py")