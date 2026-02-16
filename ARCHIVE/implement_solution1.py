#!/usr/bin/env python3
"""Implement Solution 1 for SharePoint app-only access"""

import os
import webbrowser

def implement_solution1():
    """Provide exact steps to implement Solution 1"""
    
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    
    print("🔧 IMPLEMENTING SOLUTION 1: APP-ONLY ACCESS FIX")
    print("="*80)
    
    print("📋 Current Status:")
    print(f"   Site: {SITE_URL}")
    print(f"   Client ID: {CLIENT_ID}")
    print("   ❌ App-only authentication failing with 403")
    
    print("\n" + "="*80)
    print("🎯 RECOMMENDED APPROACH: Option 4 - appinv.aspx")
    print("="*80)
    print("This is the MOST RELIABLE method for granting app access to SharePoint.")
    
    # Create the exact URL for appinv.aspx
    appinv_url = f"{SITE_URL}/_layouts/15/appinv.aspx"
    
    print(f"\n1. Open this URL in your browser:")
    print(f"   {appinv_url}")
    
    print("\n2. In the 'App Id' field, enter EXACTLY:")
    print(f"   {CLIENT_ID}")
    
    print("\n3. Click 'Lookup' button")
    print("   It should show: HM-SharepointBackup")
    
    print("\n4. In 'Permission Request XML' field, paste EXACTLY:")
    print("```xml")
    print('<AppPermissionRequests AllowAppOnlyPolicy="true">')
    print('  <AppPermissionRequest Scope="http://sharepoint/content/sitecollection" Right="FullControl" />')
    print('</AppPermissionRequests>')
    print("```")
    
    print("\n5. Click 'Create' button")
    print("   You'll see a confirmation page")
    
    print("\n6. Click 'Trust It' button")
    print("   This grants the app permission to your site")
    
    print("\n" + "="*80)
    print("🧪 TEST AFTER IMPLEMENTING:")
    print("="*80)
    print("Wait 2 minutes, then run this test:")
    print("uv run --env-file .env.sharepoint python quick_sharepoint_test.py")
    
    print("\n" + "="*80)
    print("⚠️  TROUBLESHOOTING:")
    print("="*80)
    print("If appinv.aspx doesn't work:")
    print("1. Try SharePoint Admin Center: https://honnimar-admin.sharepoint.com")
    print("2. Go to: Advanced → API access")
    print("3. Approve 'HM-SharepointBackup'")
    
    print("\n" + "="*80)
    print("📞 IF ALL APP-ONLY OPTIONS FAIL:")
    print("="*80)
    print("Use the USER authentication solution:")
    print("1. Create backup user in Azure AD")
    print("2. Grant user access to SharePoint site")
    print("3. Run: uv run --env-file .env.user sharepoint_backup_user_auth.py")
    
    # Ask if user wants to open the URL
    print("\n" + "="*80)
    response = input("Do you want to open appinv.aspx in browser now? (y/n): ")
    if response.lower() == 'y':
        print(f"Opening: {appinv_url}")
        webbrowser.open(appinv_url)

def create_quick_test():
    """Create a quick test script"""
    test_script = """#!/usr/bin/env python3
"""Quick test after implementing Solution 1"""

import os
from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext

def test_app_access():
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    
    print("🧪 Testing SharePoint App Access")
    print("="*60)
    
    try:
        credentials = ClientCredential(CLIENT_ID, CLIENT_SECRET)
        ctx = ClientContext(SITE_URL).with_credentials(credentials)
        
        web = ctx.web
        ctx.load(web, ["Title"])
        ctx.execute_query()
        
        print(f"✅ SUCCESS! Connected to: {web.properties['Title']}")
        print(f"   Site URL: {web.properties.get('Url', 'Unknown')}")
        print("\n🎉 App-only authentication is now working!")
        print("   You can run the backup script:")
        print("   uv run --env-file .env.sharepoint sharepoint_backup.py")
        return True
        
    except Exception as e:
        print(f"❌ Still failing: {str(e)[:150]}")
        print("\n⚠️  App-only access not granted yet.")
        print("   Make sure you completed all steps at appinv.aspx")
        print("   And clicked 'Trust It'")
        return False

if __name__ == "__main__":
    test_app_access()
"""
    
    with open("test_app_fix.py", "w") as f:
        f.write(test_script)
    
    print("\n📁 Created test script: test_app_fix.py")
    print("   Run after implementing Solution 1:")
    print("   uv run --env-file .env.sharepoint python test_app_fix.py")

if __name__ == "__main__":
    implement_solution1()
    create_quick_test()
    
    print("\n" + "="*80)
    print("🚀 READY TO IMPLEMENT:")
    print("="*80)
    print("1. Follow the appinv.aspx steps above")
    print("2. Wait 2 minutes for propagation")
    print("3. Run the test script")
    print("4. If successful, run the backup script")