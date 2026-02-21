        drive_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"    Processing: {drive_name}")
        
        # Get all files with metadata
        files = self._get_files_with_metadata(site_id, drive_id)
        
        if not files:
            logger.info(f"      No files found in {drive_name}")
            return
        
        logger.info(f"      Found {len(files)} files")
        
        # Filter files that need backup
        files_to_backup = []
        for file_meta in files:
            if backup_type == 'full' or self._has_file_changed(file_meta):
                files_to_backup.append(file_meta)
            else:
                self.stats['files_skipped'] += 1
        
        logger.info(f"      {len(files_to_backup)} files need backup")
        
        if not files_to_backup:
            logger.info(f"      No changes detected, skipping {drive_name}")
            return
        
        # Download files
        for file_meta in files_to_backup:
            success = self._download_file(site_id, drive_id, file_meta, drive_path)
            if not success:
                logger.warning(f"      Failed to download: {file_meta.name}")
    
    def _print_summary(self):
        """Print backup summary."""
        end_time = datetime.now()
        duration = end_time - self.stats['start_time']
        
        logger.info("=" * 60)
        logger.info("BACKUP SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Duration: {duration}")
        logger.info(f"Files backed up: {self.stats['files_backed_up']}")
        logger.info(f"Files skipped (unchanged): {self.stats['files_skipped']}")
        logger.info(f"Files failed: {self.stats['files_failed']}")
        logger.info(f"Total size: {self.stats['total_size']:,} bytes")
        
        if self.stats['bytes_saved'] > 0:
            logger.info(f"Bytes saved (incremental): {self.stats['bytes_saved']:,}")
        
        logger.info("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Optimized SharePoint Incremental Backup')
    parser.add_argument('--client-id', help='Azure AD App Client ID')
    parser.add_argument('--client-secret', help='Azure AD App Client Secret')
    parser.add_argument('--tenant-id', help='Azure AD Tenant ID')
    parser.add_argument('--backup-dir', help='Backup directory')
    parser.add_argument('--db-path', default='backup_checksums.db', help='Path to checksum database')
    parser.add_argument('--backup-type', choices=['full', 'incremental'], default='incremental',
                       help='Backup type: full or incremental (default)')
    parser.add_argument('--max-workers', type=int, default=5,
                       help='Maximum number of parallel workers (default: 5)')
    
    args = parser.parse_args()
    
    # Get credentials from environment if not provided
    client_id = args.client_id or os.environ.get('SHAREPOINT_CLIENT_ID')
    client_secret = args.client_secret or os.environ.get('SHAREPOINT_CLIENT_SECRET')
    tenant_id = args.tenant_id or os.environ.get('SHAREPOINT_TENANT_ID')
    
    if not all([client_id, client_secret, tenant_id]):
        logger.error("Missing credentials! Provide via arguments or environment variables.")
        logger.error("Required: SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET, SHAREPOINT_TENANT_ID")
        sys.exit(1)
    
    try:
        backup = OptimizedSharePointBackupWorking(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
            backup_dir=args.backup_dir,
            db_path=args.db_path
        )
        
        backup.backup_all_sites(
            backup_type=args.backup_type,
            max_workers=args.max_workers
        )
        
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()