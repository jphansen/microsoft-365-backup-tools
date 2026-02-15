#!/usr/bin/env python3
"""
Test script for Exchange/Outlook authentication
Validates Azure AD app registration and Graph API access
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def test_authentication():
    """Test authentication with Azure AD."""
    logger.info("Testing Exchange/Outlook authentication...")
    
    # Load configuration from environment
    tenant_id = os.environ.get('EXCHANGE_TENANT_ID')
    client_id = os.environ.get('EXCHANGE_CLIENT_ID')
    client_secret = os.environ.get('EXCHANGE_CLIENT_SECRET')
    
    # Check for required environment variables
    missing_vars = []
    if not tenant_id:
        missing_vars.append('EXCHANGE_TENANT_ID')
    if not client_id:
        missing_vars.append('EXCHANGE_CLIENT_ID')
    if not client_secret:
        missing_vars.append('EXCHANGE_CLIENT_SECRET')
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set these variables in your .env.exchange file")
        return False
    
    # Check for placeholder values
    if 'your-tenant-id-here' in tenant_id:
        logger.error("EXCHANGE_TENANT_ID contains placeholder value")
        logger.error("Please update with your actual Azure AD tenant ID")
        return False
    
    if 'your-client-id-here' in client_id:
        logger.error("EXCHANGE_CLIENT_ID contains placeholder value")
        logger.error("Please update with your actual Azure AD app client ID")
        return False
    
    if 'your-client-secret-here' in client_secret:
        logger.error("EXCHANGE_CLIENT_SECRET contains placeholder value")
        logger.error("Please update with your actual Azure AD app client secret")
        return False
    
    logger.info("✓ Environment variables validated")
    
    # Test authentication
    try:
        import requests
        
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': 'https://graph.microsoft.com/.default',
            'grant_type': 'client_credentials'
        }
        
        logger.info("Attempting authentication...")
        response = requests.post(token_url, data=token_data, timeout=30)
        response.raise_for_status()
        
        token_response = response.json()
        access_token = token_response.get('access_token')
        
        if not access_token:
            logger.error("No access token received in response")
            return False
        
        logger.info("✓ Authentication successful")
        logger.info(f"Token type: {token_response.get('token_type')}")
        logger.info(f"Expires in: {token_response.get('expires_in')} seconds")
        
        # Test Graph API access
        logger.info("Testing Graph API access...")
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Try to get tenant information
        graph_url = "https://graph.microsoft.com/v1.0/organization"
        response = requests.get(graph_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            org_data = response.json()
            org_name = org_data.get('value', [{}])[0].get('displayName', 'Unknown')
            logger.info(f"✓ Graph API access successful")
            logger.info(f"✓ Connected to tenant: {org_name}")
            
            # Test user access if specific user is configured
            user_email = os.environ.get('EXCHANGE_USER_EMAIL')
            if user_email:
                logger.info(f"Testing access to user: {user_email}")
                user_url = f"https://graph.microsoft.com/v1.0/users/{user_email}"
                response = requests.get(user_url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    user_data = response.json()
                    logger.info(f"✓ User access successful")
                    logger.info(f"  User: {user_data.get('displayName')} ({user_data.get('userPrincipalName')})")
                else:
                    logger.warning(f"⚠ Could not access user {user_email}")
                    logger.warning(f"  Status: {response.status_code}")
                    logger.warning(f"  Response: {response.text}")
            
            return True
        else:
            logger.error(f"Graph API access failed")
            logger.error(f"Status: {response.status_code}")
            logger.error(f"Response: {response.text}")
            
            # Provide troubleshooting tips
            if response.status_code == 401:
                logger.error("\nTroubleshooting tips:")
                logger.error("1. Check that the client secret hasn't expired")
                logger.error("2. Verify the app has required permissions (Mail.Read, User.Read.All)")
                logger.error("3. Ensure admin consent has been granted")
                logger.error("4. Wait 10-15 minutes after granting permissions")
            
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Authentication test failed: {str(e)}")
        
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return False


def test_permissions():
    """Check if required permissions are granted."""
    logger.info("\nChecking required permissions...")
    
    # Note: We can't directly check permissions via API without admin consent
    # This is just informational
    required_permissions = [
        "Mail.Read (Application)",
        "Mail.ReadWrite (Application) - Optional",
        "MailboxSettings.Read (Application) - Optional", 
        "User.Read.All (Application)"
    ]
    
    logger.info("Required permissions for Exchange backup:")
    for perm in required_permissions:
        logger.info(f"  - {perm}")
    
    logger.info("\nTo verify permissions:")
    logger.info("1. Go to Azure Portal → Azure Active Directory → App registrations")
    logger.info("2. Select your app → API permissions")
    logger.info("3. Check that all required permissions show 'Granted' status")
    logger.info("4. If not granted, click 'Grant admin consent'")
    
    return True


def main():
    """Main test function."""
    logger.info("=" * 80)
    logger.info("Exchange/Outlook Backup - Authentication Test")
    logger.info("=" * 80)
    
    # Check if .env.exchange exists
    env_file = Path(".env.exchange")
    if not env_file.exists():
        logger.error("❌ .env.exchange file not found")
        logger.error("Please create it from the template:")
        logger.error("  cp .env.exchange.example .env.exchange")
        logger.error("Then edit it with your Azure AD credentials")
        return False
    
    logger.info(f"Using environment file: {env_file.absolute()}")
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv(env_file)
    
    # Run tests
    auth_success = test_authentication()
    
    if auth_success:
        test_permissions()
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ ALL TESTS PASSED")
        logger.info("=" * 80)
        logger.info("\nNext steps:")
        logger.info("1. Run a test backup: uv run --env-file .env.exchange python exchange_backup.py --dry-run")
        logger.info("2. Run full backup: uv run --env-file .env.exchange python exchange_backup.py")
        logger.info("3. Schedule regular backups using cron or Task Scheduler")
        return True
    else:
        logger.info("\n" + "=" * 80)
        logger.error("❌ AUTHENTICATION TEST FAILED")
        logger.info("=" * 80)
        logger.info("\nTroubleshooting steps:")
        logger.info("1. Verify Azure AD app registration exists")
        logger.info("2. Check that client secret hasn't expired")
        logger.info("3. Ensure required permissions are granted with admin consent")
        logger.info("4. Wait 10-15 minutes after permission changes")
        logger.info("5. Check network connectivity to login.microsoftonline.com")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)