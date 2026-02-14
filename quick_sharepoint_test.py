#!/usr/bin/env python3
"""Quick test after fixing SharePoint permissions"""

import os
from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext

def quick_test():
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    
    print("🔧 Quick SharePoint Test")
    print("="*50)
    
    try:
        credentials = ClientCredential(CLIENT_ID, CLIENT_SECRET)
        ctx = ClientContext(SITE_URL).with_credentials(credentials)
        
        # Simple test
        web = ctx.web
        ctx.load(web, ["Title"])
        ctx.execute_query()
        
        print(f"✅ SUCCESS! Connected to: {web.properties['Title']}")
        print("\n🎉 SharePoint permissions are now working!")
        print("You can now run the backup script:")
        print("   uv run --env-file .env.sharepoint sharepoint_backup.py")
        return True
        
    except Exception as e:
        print(f"❌ Still failing: {str(e)[:200]}")
        print("\n⚠️  Make sure you:")
        print("1. Added 'Office 365 SharePoint Online' API permissions")
        print("2. Granted 'Sites.FullControl.All' (Application permission)")
        print("3. Clicked 'Grant admin consent'")
        print("4. Waited 5-10 minutes for propagation")
        return False

if __name__ == "__main__":
    quick_test()