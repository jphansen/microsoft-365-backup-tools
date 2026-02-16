#!/usr/bin/env python3
"""Decode the GUID permissions to see what SharePoint permissions are actually granted"""

import os
import requests

# Known SharePoint permission GUIDs
SHAREPOINT_PERMISSIONS = {
    # Application permissions for SharePoint Online
    "678536fe-1083-478a-9c59-b99265e6b0d3": "Sites.FullControl.All",
    "9bff6588-13f2-4c48-bbf2-ddab62256b36": "Sites.Manage.All", 
    "fbcd29d2-fcca-4405-aded-518d457caae4": "Sites.Read.All",
    "56680e0d-d2a3-4ae1-80d8-3c4f2100e3d0": "Sites.Selected",
    
    # Microsoft Graph permissions
    "332a536c-c7ef-4017-ab91-336970924f0d": "Sites.ReadWrite.All (Graph)",
    "9492366f-7969-46a4-8d15-ed1a20078fff": "Sites.Read.All (Graph)",
    "df021288-bdef-4463-88db-98f22de89214": "User.Read.All (Graph)",
}

def decode_permissions():
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    TENANT_ID = "163506f6-ef0e-42f8-a823-d13d7563bad9"
    
    print("🔍 Decoding App Permissions")
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
        
        # Get service principal
        sp_url = f"https://graph.microsoft.com/v1.0/servicePrincipals?$filter=appId eq '{CLIENT_ID}'"
        sp_response = requests.get(sp_url, headers=headers)
        
        if sp_response.status_code == 200:
            sp_data = sp_response.json()
            if sp_data['value']:
                sp_id = sp_data['value'][0]['id']
                
                # Get detailed app role assignments
                roles_url = f"https://graph.microsoft.com/v1.0/servicePrincipals/{sp_id}/appRoleAssignments"
                roles_response = requests.get(roles_url, headers=headers)
                
                if roles_response.status_code == 200:
                    roles = roles_response.json()
                    
                    print(f"\n📋 DECODED PERMISSIONS ({len(roles['value'])} total):")
                    print("-"*80)
                    
                    sharepoint_perms = []
                    graph_perms = []
                    
                    for role in roles['value']:
                        role_id = role.get('appRoleId')
                        resource = role.get('resourceDisplayName', 'Unknown')
                        permission_name = SHAREPOINT_PERMISSIONS.get(role_id, f"Unknown ({role_id})")
                        
                        if "SharePoint" in resource:
                            sharepoint_perms.append((permission_name, resource))
                        elif "Graph" in resource:
                            graph_perms.append((permission_name, resource))
                        else:
                            print(f"   • {permission_name} - {resource}")
                    
                    # Print SharePoint permissions
                    if sharepoint_perms:
                        print("\n🔷 SHAREPOINT ONLINE PERMISSIONS:")
                        for perm_name, resource in sharepoint_perms:
                            if "Sites.FullControl.All" in perm_name:
                                print(f"   ✅ {perm_name} - {resource} ✓ FULL ACCESS")
                            elif "Sites.Manage.All" in perm_name:
                                print(f"   ⚠️  {perm_name} - {resource} (Manage only)")
                            elif "Sites.Read.All" in perm_name:
                                print(f"   ❌ {perm_name} - {resource} (Read only - NOT ENOUGH)")
                            else:
                                print(f"   • {perm_name} - {resource}")
                    
                    # Print Graph permissions  
                    if graph_perms:
                        print("\n🔷 MICROSOFT GRAPH PERMISSIONS:")
                        for perm_name, resource in graph_perms:
                            print(f"   • {perm_name} - {resource}")
                    
                    # Analysis
                    print("\n" + "="*80)
                    print("ANALYSIS")
                    print("="*80)
                    
                    has_full_control = any("Sites.FullControl.All" in p[0] for p in sharepoint_perms)
                    has_manage = any("Sites.Manage.All" in p[0] for p in sharepoint_perms)
                    has_read = any("Sites.Read.All" in p[0] and "Graph" not in p[1] for p in sharepoint_perms)
                    
                    if has_full_control:
                        print("✅ You have Sites.FullControl.All permission!")
                        print("   The app should work. Possible issues:")
                        print("   1. Permissions haven't propagated (wait longer)")
                        print("   2. Site URL might be incorrect")
                        print("   3. Try the direct site access method")
                    elif has_manage:
                        print("⚠️  You have Sites.Manage.All (not FullControl)")
                        print("   This might not be enough for backup operations")
                        print("   Upgrade to Sites.FullControl.All")
                    elif has_read:
                        print("❌ You only have Sites.Read.All (read-only)")
                        print("   This is NOT enough for backup operations")
                        print("   Need Sites.FullControl.All or Sites.Manage.All")
                    else:
                        print("❌ No SharePoint write permissions found")
                        print("   Need Sites.FullControl.All or Sites.Manage.All")
                    
                    # Recommendations
                    print("\n" + "="*80)
                    print("RECOMMENDATIONS")
                    print("="*80)
                    
                    if not has_full_control:
                        print("1. Add Sites.FullControl.All permission:")
                        print("   Azure Portal → App → API permissions")
                        print("   → Office 365 SharePoint Online")
                        print("   → Application permissions → Sites.FullControl.All")
                        print("   → Grant admin consent")
                    
                    print("\n2. Try direct site access (bypasses API permissions):")
                    print("   Go to: https://honnimar.sharepoint.com/sites/DemoISM")
                    print("   → Site permissions → Grant permissions")
                    print("   → Enter: 3b1a7c1f-fbf2-4455-9e85-87f42a4e1ef3@163506f6-ef0e-42f8-a823-d13d7563bad9")
                    print("   → Full Control → Share")
                    
                    print("\n3. Wait 30+ minutes after any changes")
                    print("   Permission propagation can be slow")
                    
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    decode_permissions()