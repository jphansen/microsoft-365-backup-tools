#!/usr/bin/env python3
"""
Demonstration script showing the project is UV-controlled.
"""
import os
import sys
import subprocess
from pathlib import Path

def check_uv_installation():
    """Check if UV is installed and working."""
    print("🔧 Checking UV installation...")
    try:
        result = subprocess.run(['uv', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ UV installed: {result.stdout.strip()}")
            return True
        else:
            print("❌ UV not found or not working")
            return False
    except FileNotFoundError:
        print("❌ UV not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh")
        return False

def check_pyproject_toml():
    """Check if pyproject.toml exists and is valid."""
    print("\n📁 Checking project configuration...")
    if Path('pyproject.toml').exists():
        print("✅ pyproject.toml found")
        
        # Check basic structure
        with open('pyproject.toml', 'r') as f:
            content = f.read()
            if 'dataverse-backup-tools' in content:
                print("✅ Project name configured")
            if 'requests' in content and 'msal' in content:
                print("✅ Dependencies configured")
            if '[project.scripts]' in content:
                print("✅ Scripts configured")
        return True
    else:
        print("❌ pyproject.toml not found")
        return False

def check_uv_lock():
    """Check if uv.lock file exists."""
    print("\n🔒 Checking UV lock file...")
    if Path('uv.lock').exists():
        print("✅ uv.lock file exists")
        size = Path('uv.lock').stat().st_size
        print(f"   Size: {size:,} bytes")
        return True
    else:
        print("❌ uv.lock file not found")
        return False

def check_env_files():
    """Check if environment files exist."""
    print("\n🔐 Checking environment files...")
    env_files = ['.env.dataverse', '.env.dataverse.example', '.env.sharepoint.example']
    all_exist = True
    
    for env_file in env_files:
        if Path(env_file).exists():
            print(f"✅ {env_file} exists")
        else:
            print(f"⚠️  {env_file} not found (expected for some)")
            if env_file == '.env.dataverse':
                all_exist = False
    
    return all_exist

def check_backup_scripts():
    """Check if backup scripts exist."""
    print("\n📜 Checking backup scripts...")
    scripts = ['dataverse_backup.py', 'sharepoint_backup.py', 'test_env.py']
    all_exist = True
    
    for script in scripts:
        if Path(script).exists():
            print(f"✅ {script} exists")
        else:
            print(f"⚠️  {script} not found")
            all_exist = False
    
    return all_exist

def demonstrate_uv_usage():
    """Demonstrate UV usage examples."""
    print("\n🚀 UV Usage Examples:")
    print("=" * 50)
    
    examples = [
        ("Test environment variables", "uv run --env-file .env.dataverse test_env.py"),
        ("Run Dataverse backup", "uv run --env-file .env.dataverse dataverse_backup.py"),
        ("Run with Python directly", "uv run --env-file .env.dataverse python dataverse_backup.py"),
        ("Install dependencies", "uv sync"),
        ("Add a new dependency", "uv add pandas"),
        ("Run with specific Python version", "uv run --python 3.11 --env-file .env.dataverse dataverse_backup.py"),
    ]
    
    for description, command in examples:
        print(f"\n{description}:")
        print(f"  $ {command}")
    
    print("\n" + "=" * 50)

def main():
    print("=" * 60)
    print("Microsoft 365 Backup Tools - UV Project Demo")
    print("=" * 60)
    
    # Run checks
    checks = [
        ("UV Installation", check_uv_installation()),
        ("Project Configuration", check_pyproject_toml()),
        ("UV Lock File", check_uv_lock()),
        ("Environment Files", check_env_files()),
        ("Backup Scripts", check_backup_scripts()),
    ]
    
    print("\n" + "=" * 60)
    print("📊 Summary:")
    print("=" * 60)
    
    passed = sum(1 for _, result in checks if result)
    total = len(checks)
    
    for name, result in checks:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\n🎯 Result: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n✨ SUCCESS: Project is properly configured as a UV-controlled project!")
        demonstrate_uv_usage()
        
        print("\n📋 Next steps:")
        print("1. Configure your .env.dataverse file with actual credentials")
        print("2. Test with: uv run --env-file .env.dataverse test_env.py")
        print("3. Run backup: uv run --env-file .env.dataverse dataverse_backup.py")
        print("4. Schedule backups using cron or Task Scheduler")
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above.")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()