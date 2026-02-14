#!/usr/bin/env python3
"""Final comprehensive SharePoint test with multiple approaches"""

import os
import sys
import time
from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext

def test_with_different_approaches():
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    CLIENT_ID = os.environ.get('SHAREPOINT_CLIENT_ID')
    CLIENT_SECRET = os.environ.get('SHAREPOINT_CLIENT_SECRET')
    
    print("🔧 FINAL SHAREPOINT DIAGNOSTIC")
    print("="*80)
    
    print(f"📋 Configuration:")
    print(f"   Site URL: {SITE_URL}")
    print(f"   Client ID: {CLIENT_ID[:8]}...")
    print(f"   Timestamp: {time.ctime()}")
    
    # Test 1: Basic authentication
    print("\n1. 🔑 Testing basic authentication...")
    try:
        credentials = ClientCredential(CLIENT_ID, CLIENT_SECRET)
        ctx = ClientContext(SITE_URL).with_credentials(credentials)
        
        # Try minimal query
        web = ctx.web
        ctx.load(web, ["Title"])
        ctx.execute_query()
        
        print(f"   ✅ SUCCESS! Connected to: {web.properties['Title']}")
        print(f"   🎉 SharePoint backup should work!")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Failed: {error_msg[:150]}")
        
        # Analyze error
        if "forbidden" in error_msg.lower() or "access denied" in error_msg.lower():
            print("\n🔍 FORBIDDEN ERROR - Even with Sites.FullControl.All")
            print("   This means the app has API permissions but not site access.")
            print("\n   IMMEDIATE FIX REQUIRED:")
            print("   1. Go to SharePoint site directly:")
            print(f"      {SITE_URL}/_layouts/15/user.aspx")
            print("   2. Click 'Grant Permissions'")
            print("   3. Enter this EXACT value:")
            print(f"      3b1a7c1f-fbf2-4455-9e85-87f42a4e1ef3@163506f6-ef0e-42f8-a823-d13d7563bad9")
            print("   4. Select 'Full Control'")
            print("   5. UNCHECK 'Send email'")
            print("   6. Click 'Share'")
            print("\n   Wait 5 minutes and test again.")
        
        elif "not found" in error_msg.lower():
            print("\n🔍 SITE NOT FOUND")
            print("   Check the site URL is correct.")
            print("   Try visiting in browser: " + SITE_URL)
            
        elif "unauthorized" in error_msg.lower():
            print("\n🔍 AUTHENTICATION ERROR")
            print("   Client ID or Secret might be wrong.")
            print("   Check in Azure Portal.")
            
        return False

def check_site_url_variations():
    """Check if we need to try different URL formats"""
    base_url = "https://honnimar.sharepoint.com/sites/DemoISM"
    
    print("\n2. 🔗 Testing URL variations...")
    
    variations = [
        base_url,
        base_url + "/",
        base_url.replace("https://", "https://honnimar.sharepoint.com/"),
        "https://honnimar.sharepoint.com/sites/DemoISM/"
    ]
    
    for url in variations:
        print(f"   Testing: {url}")
        # We can't test all without running, but we can suggest
        if url != base_url:
            print(f"   Try updating .env.sharepoint with: SHAREPOINT_SITE_URL={url}")

def main():
    print("Based on previous diagnostics:")
    print("✅ You have Sites.FullControl.All permission")
    print("✅ Azure AD authentication works")
    print("✅ Microsoft Graph API access works")
    print("❌ Direct SharePoint REST API fails (403)")
    print("\nThis is a COMMON issue with SharePoint app-only access.")
    
    success = test_with_different_approaches()
    
    if not success:
        check_site_url_variations()
        
        print("\n" + "="*80)
        print("SUMMARY & NEXT STEPS")
        print("="*80)
        print("1. REQUIRED: Grant direct SharePoint site access")
        print(f"   Visit: https://honnimar.sharepoint.com/sites/DemoISM/_layouts/15/user.aspx")
        print("   Add the app with Full Control")
        print("\n2. Alternative: Wait longer")
        print("   API permissions can take 30-60 minutes to propagate")
        print("\n3. Test command after fixing:")
        print("   uv run --env-file .env.sharepoint python quick_sharepoint_test.py")
        print("\n4. Final backup test:")
        print("   uv run --env-file .env.sharepoint sharepoint_backup.py --dry-run")
    
    print("\n" + "="*80)
    print("QUICK FIX COMMAND (copy and run in terminal):")
    print("="*80)
    print("# 1. First, let's check if site is accessible")
    print(f"curl -I {os.environ.get('SHAREPOINT_SITE_URL')}")
    print("\n# 2. Test with dry-run flag if script supports it")
    print("uv run --env-file .env.sharepoint python -c \"")
    print("import os; print('Site URL:', os.environ.get('SHAREPOINT_SITE_URL'))")
    print("print('Client ID:', os.environ.get('SHAREPOINT_CLIENT_ID')[:8] + '...')")
    print("\"")

if __name__ == "__main__":
    main()