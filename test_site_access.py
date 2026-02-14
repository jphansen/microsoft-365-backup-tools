#!/usr/bin/env python3
"""Test if SharePoint site is accessible and try alternative authentication"""

import os
import requests
import json

def test_site_access():
    """Test basic site accessibility"""
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    
    print("🔍 Testing SharePoint Site Accessibility")
    print("="*80)
    
    # Test 1: Basic HTTP access
    print(f"1. Testing HTTP access to: {SITE_URL}")
    try:
        response = requests.get(SITE_URL, timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Site is accessible via browser")
        else:
            print(f"   ⚠️  Site returned: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Cannot access site: {str(e)}")
    
    # Test 2: Try with trailing slash
    print(f"\n2. Testing with trailing slash: {SITE_URL}/")
    try:
        response = requests.get(SITE_URL + "/", timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✅ Try updating .env.sharepoint with trailing slash")
            print(f"   SHAREPOINT_SITE_URL={SITE_URL}/")
    except Exception as e:
        print(f"   ❌ Cannot access: {str(e)}")
    
    # Test 3: Check SharePoint REST API directly
    print(f"\n3. Testing SharePoint REST API endpoint")
    api_url = f"{SITE_URL}/_api/web?$select=Title"
    try:
        response = requests.get(api_url, timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 403:
            print("   ❌ REST API returns 403 - App needs site permissions")
        elif response.status_code == 401:
            print("   ❌ REST API returns 401 - Authentication issue")
        elif response.status_code == 200:
            print("   ✅ REST API accessible (unexpected - should require auth)")
    except Exception as e:
        print(f"   ❌ API error: {str(e)}")

def provide_workaround():
    """Provide workaround if direct site access fails"""
    print("\n" + "="*80)
    print("WORKAROUND: Use App-Only Certificate Authentication")
    print("="*80)
    
    print("If granting site access fails, try certificate authentication:")
    print("\n1. Generate a self-signed certificate:")
    print("   openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes")
    
    print("\n2. Upload certificate to Azure AD:")
    print("   - Go to Azure Portal → App registrations → HM-SharepointBackup")
    print("   - Certificates & secrets → Certificates → Upload certificate")
    print("   - Upload cert.pem")
    
    print("\n3. Update sharepoint_backup.py to use certificate auth:")
    print("   Replace ClientCredential with CertificateCredential")
    
    print("\n" + "="*80)
    print("IMMEDIATE TEST - Try different site URL:")
    print("="*80)
    
    SITE_URL = os.environ.get('SHAREPOINT_SITE_URL')
    variations = [
        SITE_URL,
        SITE_URL + "/",
        SITE_URL.replace("https://", ""),
        "https://" + SITE_URL.split("//")[1] if "//" in SITE_URL else SITE_URL
    ]
    
    print("Try these URLs in .env.sharepoint:")
    for url in set(variations):
        print(f"   SHAREPOINT_SITE_URL={url}")

if __name__ == "__main__":
    test_site_access()
    provide_workaround()
    
    print("\n" + "="*80)
    print("NEXT STEPS SUMMARY:")
    print("="*80)
    print("1. Try SharePoint Admin Center method")
    print("2. Wait 1 hour for permission propagation")
    print("3. Try trailing slash in URL")
    print("4. Consider certificate authentication as last resort")