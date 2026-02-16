#!/usr/bin/env python3
"""
Test script for Exchange/Outlook backup functionality
Tests basic backup operations without actually downloading emails
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


def test_configuration():
    """Test configuration loading and validation."""
    logger.info("Testing configuration...")
    
    try:
        # Import the actual configuration functions
        from exchange_backup import load_config, validate_config
        
        config = load_config()
        
        # Check required fields
        required_fields = ['EXCHANGE_TENANT_ID', 'EXCHANGE_CLIENT_ID', 'EXCHANGE_CLIENT_SECRET']
        missing_fields = [field for field in required_fields if not config.get(field)]
        
        if missing_fields:
            logger.error(f"Missing required configuration fields: {', '.join(missing_fields)}")
            return False
        
        # Validate configuration
        if not validate_config(config):
            logger.error("Configuration validation failed")
            return False
        
        logger.info("✓ Configuration loaded and validated")
        
        # Log configuration (without secrets)
        safe_config = config.copy()
        if safe_config.get('EXCHANGE_CLIENT_SECRET'):
            safe_config['EXCHANGE_CLIENT_SECRET'] = '***' + safe_config['EXCHANGE_CLIENT_SECRET'][-4:] if len(safe_config['EXCHANGE_CLIENT_SECRET']) > 4 else '***'
        
        logger.debug("Configuration:")
        for key, value in safe_config.items():
            logger.debug(f"  {key}: {value}")
        
        return True
        
    except Exception as e:
        logger.error(f"Configuration test failed: {str(e)}")
        return False


def test_authentication():
    """Test authentication with Azure AD."""
    logger.info("Testing authentication...")
    
    try:
        from exchange_backup import ExchangeBackup, load_config
        
        config = load_config()
        
        # Create backup instance (will authenticate)
        backup = ExchangeBackup(config)
        
        if not backup.access_token:
            logger.error("No access token obtained")
            return False
        
        logger.info("✓ Authentication successful")
        logger.info(f"Access token obtained: {backup.access_token[:20]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"Authentication test failed: {str(e)}")
        return False


def test_graph_api_access():
    """Test Graph API access."""
    logger.info("Testing Graph API access...")
    
    try:
        from exchange_backup import ExchangeBackup, load_config
        
        config = load_config()
        backup = ExchangeBackup(config)
        
        # Test getting users
        logger.info("Testing user enumeration...")
        users = backup._get_users()
        
        if not users:
            logger.warning("No users found - this might be expected if EXCHANGE_USER_EMAIL is set")
        else:
            logger.info(f"✓ Found {len(users)} users")
            for user in users[:3]:  # Show first 3 users
                logger.info(f"  - {user.get('userPrincipalName')} ({user.get('displayName')})")
            if len(users) > 3:
                logger.info(f"  ... and {len(users) - 3} more")
        
        # Test getting folders for first user (if available)
        if users:
            user_id = users[0].get('id')
            logger.info(f"Testing folder enumeration for user: {users[0].get('userPrincipalName')}")
            
            folders = backup._get_user_folders(user_id)
            if folders:
                logger.info(f"✓ Found {len(folders)} folders")
                for folder in folders[:5]:  # Show first 5 folders
                    logger.info(f"  - {folder.get('displayName')} ({folder.get('id')})")
                if len(folders) > 5:
                    logger.info(f"  ... and {len(folders) - 5} more")
            else:
                logger.warning("No folders found - user might not have mailbox enabled")
        
        logger.info("✓ Graph API access successful")
        return True
        
    except Exception as e:
        logger.error(f"Graph API test failed: {str(e)}")
        return False


def test_backup_directory():
    """Test backup directory creation."""
    logger.info("Testing backup directory setup...")
    
    try:
        from exchange_backup import ExchangeBackup, load_config
        
        config = load_config()
        backup = ExchangeBackup(config)
        
        if not backup.backup_path:
            logger.error("Backup path not created")
            return False
        
        if not backup.backup_path.exists():
            logger.error(f"Backup directory does not exist: {backup.backup_path}")
            return False
        
        logger.info(f"✓ Backup directory created: {backup.backup_path}")
        
        # Check permissions
        try:
            test_file = backup.backup_path / "test_permissions.txt"
            test_file.write_text("Test")
            test_file.unlink()
            logger.info("✓ Write permissions verified")
        except Exception as e:
            logger.error(f"Write permission test failed: {str(e)}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Backup directory test failed: {str(e)}")
        return False


def test_dry_run():
    """Test dry run mode (no actual backup)."""
    logger.info("Testing dry run mode...")
    
    try:
        # Modify config for dry run
        import copy
        from exchange_backup import ExchangeBackup, load_config
        
        config = load_config()
        
        # Set limits for testing
        test_config = copy.deepcopy(config)
        test_config['EXCHANGE_MAX_EMAILS_PER_BACKUP'] = 5  # Limit to 5 emails
        test_config['EXCHANGE_INCLUDE_ATTACHMENTS'] = False  # Skip attachments
        
        backup = ExchangeBackup(test_config)
        
        # Get users
        users = backup._get_users()
        if not users:
            logger.warning("No users found - cannot test dry run")
            return True  # Not a failure, just no data
        
        # Test with first user
        user = users[0]
        user_id = user.get('id')
        
        logger.info(f"Testing dry run for user: {user.get('userPrincipalName')}")
        
        # Get folders
        folders = backup._get_user_folders(user_id)
        if not folders:
            logger.warning("No folders found - cannot test message retrieval")
            return True  # Not a failure
        
        # Get messages from first folder
        folder = folders[0]
        messages = backup._get_folder_messages(user_id, folder.get('id'))
        
        if messages:
            logger.info(f"✓ Found {len(messages)} messages in folder '{folder.get('displayName')}'")
            
            # Test message processing (without saving)
            for i, message in enumerate(messages[:3]):  # Test first 3 messages
                subject = message.get('subject', 'No Subject')
                logger.info(f"  Message {i+1}: {subject[:50]}...")
                
                # Test attachment check
                if message.get('hasAttachments', False):
                    attachments = backup._get_message_attachments(user_id, message.get('id'))
                    logger.info(f"    Has {len(attachments)} attachments")
                
                # Test checksum calculation
                checksum = backup._calculate_checksum(message)
                logger.info(f"    Checksum: {checksum[:16]}...")
        
        logger.info("✓ Dry run completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Dry run test failed: {str(e)}")
        return False


def main():
    """Run all tests."""
    logger.info("=" * 80)
    logger.info("Exchange/Outlook Backup - Functional Test Suite")
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
    tests = [
        ("Configuration", test_configuration),
        ("Authentication", test_authentication),
        ("Graph API Access", test_graph_api_access),
        ("Backup Directory", test_backup_directory),
        ("Dry Run", test_dry_run),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n{'='*40}")
        logger.info(f"Test: {test_name}")
        logger.info(f"{'='*40}")
        
        try:
            success = test_func()
            results.append((test_name, success))
            
            if success:
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.error(f"❌ {test_name}: FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name}: ERROR - {str(e)}")
            results.append((test_name, False))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"{test_name:30} {status}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n" + "=" * 80)
        logger.info("✅ ALL TESTS PASSED")
        logger.info("=" * 80)
        logger.info("\nNext steps:")
        logger.info("1. Run a full backup: uv run --env-file .env.exchange python exchange_backup.py")
        logger.info("2. Check backup logs: tail -f exchange_backup.log")
        logger.info("3. Verify backup files in: backup/exchange/")
        logger.info("4. Schedule regular backups using cron or Task Scheduler")
        return True
    else:
        logger.info("\n" + "=" * 80)
        logger.error("❌ SOME TESTS FAILED")
        logger.info("=" * 80)
        logger.info("\nTroubleshooting:")
        logger.info("1. Check Azure AD app registration and permissions")
        logger.info("2. Verify client secret hasn't expired")
        logger.info("3. Ensure required Graph API permissions are granted")
        logger.info("4. Check network connectivity to Graph API")
        logger.info("5. Review detailed logs above for specific errors")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)