#!/usr/bin/env python3
"""Test user authentication for SharePoint backup"""

import os
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext

def test_user_authentication():
    """Test SharePoint authentication with user credentials"""
    
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    USERNAME = os.environ.get('SHAREPOINT_USERNAME')
    PASSWORD = os.environ.get('SHAREPOINT_PASSWORD')
    
    print("🔧 Testing SharePoint User Authentication")
    print("="*80)
    
    if not USERNAME or not PASSWORD:
        print("❌ Missing user credentials!")
        print("   Set these environment variables:")
        print("   SHAREPOINT_USERNAME=your-user@honnimar.onmicrosoft.com")
        print("   SHAREPOINT_PASSWORD=your-password")
        print("\n   Or create a new .env.user file:")
        print("   SHAREPOINT_SITE_URL=https://honnimar.sharepoint.com/sites/DemoISM")
        print("   SHAREPOINT_USERNAME=your-user@honnimar.onmicrosoft.com")
        print("   SHAREPOINT_PASSWORD=your-password")
        print("   BACKUP_DIR=backup/sharepoint")
        return False
    
    print(f"📋 Configuration:")
    print(f"   Site: {SITE_URL}")
    print(f"   User: {USERNAME}")
    
    try:
        print("\n🔑 Attempting user authentication...")
        credentials = UserCredential(USERNAME, PASSWORD)
        ctx = ClientContext(SITE_URL).with_credentials(credentials)
        
        # Test connection
        web = ctx.web
        ctx.load(web, ["Title", "Url"])
        ctx.execute_query()
        
        print(f"\n✅ SUCCESS! User authentication working!")
        print(f"   Connected to: {web.properties['Title']}")
        print(f"   Site URL: {web.properties['Url']}")
        
        # Test list access
        lists = web.lists
        ctx.load(lists)
        ctx.execute_query()
        
        print(f"   Found {len(lists)} lists/libraries")
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Authentication failed: {error_msg[:200]}")
        
        print("\n🔧 Troubleshooting tips:")
        
        if "invalid username or password" in error_msg.lower():
            print("1. Check username and password")
            print("2. Try logging into SharePoint with these credentials")
            
        elif "multi-factor authentication" in error_msg.lower() or "mfa" in error_msg.lower():
            print("1. MFA is enabled - you need an app password")
            print("2. Go to https://mysignins.microsoft.com/security-info")
            print("3. Create an app password")
            print("4. Use that password instead of your regular password")
            
        elif "access denied" in error_msg.lower() or "forbidden" in error_msg.lower():
            print("1. User doesn't have access to this SharePoint site")
            print("2. Grant user access to the site first")
            print("3. Visit the site in browser to check access")
            
        elif "cannot contact site" in error_msg.lower() or "not found" in error_msg.lower():
            print("1. Site URL might be incorrect")
            print("2. Check if site exists: " + SITE_URL)
            
        else:
            print("1. Check all credentials are correct")
            print("2. Ensure user has SharePoint access")
            print("3. Try disabling MFA temporarily for testing")
        
        return False

def create_user_env_file():
    """Create a sample .env.user file"""
    content = """# SharePoint Backup - User Authentication
# Use this when app-only authentication fails

# SharePoint Site URL
SHAREPOINT_SITE_URL=https://honnimar.sharepoint.com/sites/DemoISM

# User Credentials (must have access to the site)
SHAREPOINT_USERNAME=your-user@honnimar.onmicrosoft.com
SHAREPOINT_PASSWORD=your-password-here

# Backup Configuration
BACKUP_DIR=backup/sharepoint

# Instructions:
# 1. Create a dedicated user in Azure AD for backups
# 2. Grant that user access to the SharePoint site
# 3. Use those credentials here
# 4. Run: uv run --env-file .env.user sharepoint_backup_user_auth.py
"""
    
    print("\n" + "="*80)
    print("📁 SAMPLE .env.user FILE:")
    print("="*80)
    print(content)

if __name__ == "__main__":
    print("Since app-only authentication is failing, let's try USER authentication.")
    print("This is often easier to set up for SharePoint access.")
    
    success = test_user_authentication()
    
    if not success:
        create_user_env_file()
        
        print("\n" + "="*80)
        print("🎯 QUICK SETUP INSTRUCTIONS:")
        print("="*80)
        print("1. Create a backup user in Azure AD:")
        print("   - Name: sharepoint-backup@honnimar.onmicrosoft.com")
        print("   - Password: (create strong password)")
        print("   - Disable MFA for this user (or use app password)")
        
        print("\n2. Grant user access to SharePoint site:")
        print("   - Go to: https://honnimar.sharepoint.com/sites/DemoISM")
        print("   - Site permissions → Grant permissions")
        print("   - Add the user email")
        print("   - Select 'Full Control'")
        
        print("\n3. Create .env.user file:")
        print("   cp .env.sharepoint .env.user")
        print("   Edit .env.user to add:")
        print("   SHAREPOINT_USERNAME=sharepoint-backup@honnimar.onmicrosoft.com")
        print("   SHAREPOINT_PASSWORD=YourPassword123")
        
        print("\n4. Test user authentication:")
        print("   uv run --env-file .env.user python test_user_auth.py")
        
        print("\n5. Run backup with user auth:")
        print("   uv run --env-file .env.user sharepoint_backup_user_auth.py")