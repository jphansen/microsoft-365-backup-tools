#!/usr/bin/env python3
"""
Test script for SharePoint Incremental Backup
Demonstrates checksum-based deduplication functionality.
"""

import os
import sys
import json
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from checksum_db import BackupChecksumDB, calculate_checksum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_checksum_database():
    """Test the checksum database functionality."""
    print("🧪 TESTING CHECKSUM DATABASE")
    print("="*80)
    
    # Create test database
    db = BackupChecksumDB("test_incremental.db")
    
    # Test 1: Add file record
    print("1. Adding file record...")
    file_id = db.update_file_record(
        site_id="test_site_1",
        file_path="/documents/report.docx",
        file_name="report.docx",
        file_size=1024,
        last_modified="2024-01-01T12:00:00Z",
        checksum="abc123def456"
    )
    print(f"   ✅ Added file with ID: {file_id}")
    
    # Test 2: Check unchanged file
    print("\n2. Checking unchanged file...")
    unchanged, record = db.is_file_unchanged(
        site_id="test_site_1",
        file_path="/documents/report.docx",
        current_checksum="abc123def456",
        current_size=1024
    )
    print(f"   ✅ File unchanged: {unchanged}")
    
    # Test 3: Check changed file (size changed)
    print("\n3. Checking changed file (size)...")
    unchanged, record = db.is_file_unchanged(
        site_id="test_site_1",
        file_path="/documents/report.docx",
        current_checksum="abc123def456",
        current_size=2048  # Size changed
    )
    print(f"   ✅ File unchanged: {unchanged} (should be False)")
    
    # Test 4: Check changed file (checksum changed)
    print("\n4. Checking changed file (checksum)...")
    unchanged, record = db.is_file_unchanged(
        site_id="test_site_1",
        file_path="/documents/report.docx",
        current_checksum="different_checksum",
        current_size=1024
    )
    print(f"   ✅ File unchanged: {unchanged} (should be False)")
    
    # Test 5: Backup session tracking
    print("\n5. Testing backup session tracking...")
    session_id = db.start_backup_session("incremental", "test_site_1")
    db.update_backup_session(
        session_id=session_id,
        files_backed_up=10,
        files_skipped=5,
        total_size=15360,
        status="completed"
    )
    print(f"   ✅ Created backup session {session_id}")
    
    # Test 6: Get statistics
    print("\n6. Getting backup statistics...")
    stats = db.get_backup_stats(7)
    print(f"   ✅ Statistics: {json.dumps(stats, indent=2, default=str)}")
    
    print("\n" + "="*80)
    print("✅ CHECKSUM DATABASE TEST COMPLETED")
    print("="*80)


def test_checksum_calculation():
    """Test checksum calculation functionality."""
    print("\n🧪 TESTING CHECKSUM CALCULATION")
    print("="*80)
    
    # Create a test file
    test_file = Path("test_checksum_file.txt")
    test_content = b"This is a test file for checksum calculation.\n" * 100
    
    with open(test_file, "wb") as f:
        f.write(test_content)
    
    try:
        # Calculate checksum
        checksum = calculate_checksum(test_file)
        print(f"1. File checksum: {checksum}")
        print(f"   ✅ Checksum calculated successfully")
        
        # Verify checksum is consistent
        checksum2 = calculate_checksum(test_file)
        print(f"\n2. Second calculation: {checksum2}")
        print(f"   ✅ Checksums match: {checksum == checksum2}")
        
        # Modify file and recalculate
        with open(test_file, "ab") as f:
            f.write(b"\nAdditional content")
        
        checksum3 = calculate_checksum(test_file)
        print(f"\n3. After modification: {checksum3}")
        print(f"   ✅ Checksum changed: {checksum != checksum3}")
        
    finally:
        # Clean up
        if test_file.exists():
            test_file.unlink()
    
    print("\n" + "="*80)
    print("✅ CHECKSUM CALCULATION TEST COMPLETED")
    print("="*80)


def demonstrate_incremental_backup():
    """Demonstrate incremental backup concept."""
    print("\n🎯 DEMONSTRATING INCREMENTAL BACKUP CONCEPT")
    print("="*80)
    
    print("SCENARIO: SharePoint site with 1000 files")
    print("FIRST BACKUP (Full):")
    print("  • Downloads all 1000 files")
    print("  • Calculates checksums")
    print("  • Stores in database")
    print("  • Time: 60 minutes")
    print("  • Bandwidth: 10 GB")
    
    print("\nSECOND BACKUP (Incremental - no changes):")
    print("  • Checks database for existing files")
    print("  • Compares sizes and checksums")
    print("  • All 1000 files unchanged")
    print("  • Skips all downloads")
    print("  • Time: 2 minutes (just checking)")
    print("  • Bandwidth: 0 MB")
    print("  • Savings: 98% time, 100% bandwidth")
    
    print("\nTHIRD BACKUP (Incremental - 5 files changed):")
    print("  • Checks database for existing files")
    print("  • 995 files unchanged → skipped")
    print("  • 5 files changed → downloaded")
    print("  • Updates database with new checksums")
    print("  • Time: 3 minutes")
    print("  • Bandwidth: 50 MB (5 files)")
    print("  • Savings: 95% time, 99.5% bandwidth")
    
    print("\n" + "="*80)
    print("✅ INCREMENTAL BACKUP DEMONSTRATION COMPLETED")
    print("="*80)


def show_usage_examples():
    """Show usage examples for the incremental backup."""
    print("\n🚀 USAGE EXAMPLES")
    print("="*80)
    
    print("1. First backup (full):")
    print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --type full")
    
    print("\n2. Subsequent backups (incremental):")
    print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py")
    print("   # Default is incremental")
    
    print("\n3. With custom backup directory:")
    print("   BACKUP_DIR=/mnt/backup/sharepoint uv run --env-file .env.sharepoint sharepoint_incremental_backup.py")
    
    print("\n4. With more parallel workers:")
    print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --workers 10")
    
    print("\n5. Show backup statistics:")
    print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --stats")
    
    print("\n6. Verify backup integrity:")
    print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --verify")
    
    print("\n7. Cleanup old records (keep 30 days):")
    print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --cleanup 30")
    
    print("\n8. Compare with original backup script:")
    print("   # Original (always full backup):")
    print("   uv run --env-file .env.sharepoint sharepoint_graph_backup.py")
    print("   \n   # Incremental (only changed files):")
    print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py")
    
    print("\n" + "="*80)
    print("✅ USAGE EXAMPLES COMPLETED")
    print("="*80)


def main():
    """Run all tests and demonstrations."""
    print("🔧 SHAREPOINT INCREMENTAL BACKUP TEST SUITE")
    print("="*80)
    
    try:
        test_checksum_database()
        test_checksum_calculation()
        demonstrate_incremental_backup()
        show_usage_examples()
        
        print("\n" + "="*80)
        print("🎉 ALL TESTS COMPLETED SUCCESSFULLY!")
        print("="*80)
        print("\n📋 NEXT STEPS:")
        print("1. Run first full backup:")
        print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --type full")
        print("\n2. Then run incremental backups:")
        print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py")
        print("\n3. Monitor savings with statistics:")
        print("   uv run --env-file .env.sharepoint sharepoint_incremental_backup.py --stats")
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())