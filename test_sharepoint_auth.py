#!/usr/bin/env python3
"""Test SharePoint authentication for backup script"""

import os
import sys
from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext

def test_authentication():
    """Test SharePoint authentication with current environment variables."""
    
    # Load from environment
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    
    print("=" * 60)
    print("SharePoint Authentication Test")
    print("=" * 60)
    
    # Check for placeholder values
    if not SITE_URL or not CLIENT_ID or not CLIENT_SECRET:
        print("❌ Missing environment variables!")
        print(f"   SHAREPOINT_SITE_URL: {'Set' if SITE_URL else 'Missing'}")
        print(f"   SHAREPOINT_CLIENT_ID: {'Set' if CLIENT_ID else 'Missing'}")
        print(f"   SHAREPOINT_CLIENT_SECRET: {'Set' if CLIENT_SECRET else 'Missing'}")
        return False
    
    if 'your-tenant' in SITE_URL or 'your-client-id' in CLIENT_ID:
        print("❌ Using placeholder values!")
        print("   Please update .env.sharepoint with real credentials")
        return False
    
    print(f"🔗 Testing connection to: {SITE_URL}")
    print(f"📋 Client ID: {CLIENT_ID[:10]}...")
    print(f"🔐 Client Secret: {'*' * len(CLIENT_SECRET) if CLIENT_SECRET else 'Missing'}")
    
    try:
        print("\n🔑 Attempting authentication...")
        credentials = ClientCredential(CLIENT_ID, CLIENT_SECRET)
        ctx = ClientContext(SITE_URL).with_credentials(credentials)
        
        # Try to get site info
        print("📡 Querying site information...")
        web = ctx.web
        ctx.load(web)
        ctx.execute_query()
        
        print("\n" + "=" * 60)
        print("✅ SUCCESS! Authentication successful!")
        print("=" * 60)
        print(f"   Site Title: {web.properties.get('Title', 'Unknown')}")
        print(f"   Site URL: {web.properties.get('Url', 'Unknown')}")
        print(f"   Created: {web.properties.get('Created', 'Unknown')}")
        print(f"   Language: {web.properties.get('Language', 'Unknown')}")
        
        # Test list access
        print("\n📋 Testing list access...")
        lists = web.lists
        ctx.load(lists)
        ctx.execute_query()
        
        print(f"   Found {len(lists)} lists/libraries")
        
        # Show first few lists
        for i, list_obj in enumerate(lists[:5]):
            print(f"   {i+1}. {list_obj.properties.get('Title')} "
                  f"(Template: {list_obj.properties.get('BaseTemplate')})")
        
        if len(lists) > 5:
            print(f"   ... and {len(lists) - 5} more")
        
        return True
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ AUTHENTICATION FAILED!")
        print("=" * 60)
        print(f"Error: {str(e)}")
        
        # Provide troubleshooting tips based on error
        error_msg = str(e).lower()
        
        print("\n🔧 Troubleshooting tips:")
        
        if "unauthorized" in error_msg or "access denied" in error_msg:
            print("1. Check API permissions in Azure AD:")
            print("   - Ensure 'Sites.ReadWrite.All' is granted")
            print("   - Admin consent must be granted")
            print("2. Verify app has access to the SharePoint site")
            print("3. Wait 5-10 minutes after granting permissions")
            
        elif "invalid client secret" in error_msg or "bad request" in error_msg:
            print("1. Client secret may be expired or incorrect")
            print("2. Create a new client secret in Azure AD")
            print("3. Update .env.sharepoint with the new secret")
            
        elif "not found" in error_msg or "404" in error_msg:
            print("1. Check SHAREPOINT_SITE_URL is correct")
            print("2. Verify the site exists and is accessible")
            print("3. Ensure URL format is: https://tenant.sharepoint.com/sites/sitename")
            
        elif "timeout" in error_msg:
            print("1. Network/firewall issue")
            print("2. Check internet connectivity")
            print("3. Verify proxy settings if applicable")
            
        else:
            print("1. Verify all credentials are correct")
            print("2. Check Azure AD app registration configuration")
            print("3. Ensure SharePoint site is online and accessible")
        
        return False

if __name__ == "__main__":
    print("Loading environment from .env.sharepoint...")
    
    # Check if .env.sharepoint exists
    if not os.path.exists('.env.sharepoint'):
        print("❌ .env.sharepoint file not found!")
        print("   Create it from .env.sharepoint.example")
        sys.exit(1)
    
    success = test_authentication()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Ready to run backup!")
        print("   Command: uv run --env-file .env.sharepoint sharepoint_backup.py")
    else:
        print("⚠️  Fix the issues above before running backup")
    print("=" * 60)
    
    sys.exit(0 if success else 1)