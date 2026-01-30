#!/usr/bin/env python3
"""
Test script to verify environment variable loading.
"""
import os

print("Testing environment variable loading...")
print("=" * 50)

# Check all required environment variables
env_vars = [
    'DATAVERSE_ENVIRONMENT_URL',
    'DATAVERSE_TENANT_ID', 
    'DATAVERSE_CLIENT_ID',
    'DATAVERSE_CLIENT_SECRET'
]

all_present = True
for var in env_vars:
    value = os.environ.get(var)
    if value:
        # Mask secret for display
        if 'SECRET' in var:
            display_value = '*' * len(value)
        else:
            display_value = value
        print(f"✓ {var}: {display_value}")
    else:
        print(f"✗ {var}: NOT SET")
        all_present = False

print("=" * 50)
if all_present:
    print("SUCCESS: All environment variables are set!")
    print("\nTo run the backup:")
    print("  uv run --env-file .env.dataverse dataverse_backup.py")
else:
    print("ERROR: Some environment variables are missing.")
    print("\nMake sure to run with:")
    print("  uv run --env-file .env.dataverse test_env.py")