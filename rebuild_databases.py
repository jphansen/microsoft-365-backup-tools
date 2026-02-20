#!/usr/bin/env python3
"""
Database Rebuild Tool for Microsoft 365 Backup
================================================
Traverses the local backup file tree and (re)builds the SQLite checksum
databases from what is actually present on disk – without touching Microsoft
Graph or any online service.

SharePoint database  (backup_checksums.db)
  Records every backed-up file with its SHA-256 checksum, size and mtime.

Exchange database    (backup_checksums_exchange.db)
  Records every backed-up email (.eml / .json) with its SHA-256 checksum
  and, where possible, extracted message metadata.

Expected backup tree layout
----------------------------
  <backup_dir>/
    [sharepoint/]                 <- optional sub-folder grouping
      <site_name>/
        <YYYYMMDD_HHMMSS>/
          site_metadata.json      <- contains Graph site_id
          <drive_folder>/
            drive_metadata.json
            <files and sub-dirs …>

    exchange/
      <user>/
        <YYYYMMDD_HHMMSS>/
          user_metadata.json      <- optional, contains userPrincipalName
          <Folder>/
            <subject>_<msg_id>.eml
            <subject>_<msg_id>.json

Usage examples
--------------
  # Rebuild both DBs (default paths, backup/ as root)
  python rebuild_databases.py

  # SharePoint only
  python rebuild_databases.py --type sharepoint

  # Exchange only
  python rebuild_databases.py --type exchange

  # Custom paths + dry-run
  python rebuild_databases.py --backup-dir /mnt/nas/backup \\
      --sharepoint-db /data/sp.db --exchange-db /data/ex.db --dry-run -v
"""

import email as email_module
import email.policy
import hashlib
import json
import logging
import os
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metadata / helper files that must never be treated as backed-up content
# ---------------------------------------------------------------------------
_SKIP_FILENAMES = frozenset({
    "site_metadata.json",
    "drive_metadata.json",
    "backup_statistics.json",
    "backup_manifest.json",
    "user_metadata.json",
})

_SKIP_SUFFIXES = frozenset({".log", ".db", ".db-wal", ".db-shm"})


# ===========================================================================
# Generic helpers
# ===========================================================================

def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return the hex-encoded SHA-256 checksum of a file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            buf = fh.read(chunk_size)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def human_size(n: int) -> str:
    """Return a human-readable byte count string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ===========================================================================
# Exchange-specific helpers
# ===========================================================================

def parse_eml_headers(path: Path) -> Dict[str, str]:
    """Return a dict of useful headers from an EML file (fast, no body read)."""
    try:
        with open(path, "rb") as fh:
            msg = email_module.message_from_binary_file(
                fh, policy=email_module.policy.compat32
            )
        return {
            "subject":          str(msg.get("Subject", "")),
            "sender":           str(msg.get("From", "")),
            "received_date":    str(msg.get("Date", "")),
            "message_id_hdr":   str(msg.get("Message-ID", "")),
        }
    except Exception as exc:
        logger.debug(f"    Could not parse EML headers from {path.name}: {exc}")
        return {}


def extract_msg_id_from_stem(stem: str) -> Tuple[str, str]:
    """
    Best-effort extraction of (subject_part, message_id_part) from a filename
    stem of the form  ``{safe_subject}_{safe_message_id}``.

    Exchange Graph API message IDs typically start with "AAMk" when encoded.
    We look for that pattern first, then fall back to using the whole stem.
    """
    match = re.search(r'_(AAMk[A-Za-z0-9_-]{10,})$', stem)
    if match:
        msg_id_safe  = match.group(1)
        subject_safe = stem[: match.start()].strip("_")
        return subject_safe, msg_id_safe
    # Fallback
    return stem, stem


# ===========================================================================
# SharePoint rebuild
# ===========================================================================

def rebuild_sharepoint_db(
    backup_root: Path,
    db_path: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Walk *backup_root* looking for ``site_metadata.json`` files (one per
    backup session), then index every content file in that session into the
    SharePoint checksum database.

    Only the **most recent session** for each ``(site_id, relative_path)``
    pair ends up in the DB – older sessions are processed first and the later
    upsert wins automatically.
    """
    from checksum_db import BackupChecksumDB      # lazy import

    stats: Dict[str, Any] = {
        "sites_found":      0,
        "sessions_found":   0,
        "files_scanned":    0,
        "files_written":    0,
        "files_skipped":    0,
        "files_errors":     0,
        "total_bytes":      0,
    }

    db = None if dry_run else BackupChecksumDB(db_path)

    # rglob finds all sessions regardless of nesting (backup/ or backup/sharepoint/)
    # Sort so older timestamps are processed before newer ones.
    meta_files = sorted(backup_root.rglob("site_metadata.json"))
    if not meta_files:
        logger.warning(f"No site_metadata.json found under {backup_root}")
        return stats

    for meta_path in meta_files:
        # Exclude anything inside the exchange sub-tree
        if "exchange" in meta_path.parts:
            continue

        session_dir = meta_path.parent
        try:
            with open(meta_path, encoding="utf-8") as fh:
                meta = json.load(fh)
        except Exception as exc:
            logger.warning(f"  Could not read {meta_path}: {exc}")
            continue

        site_id   = meta.get("site_id", f"unknown:{session_dir.parent.name}")
        site_name = meta.get("site_name", session_dir.parent.name)
        timestamp = session_dir.name

        stats["sessions_found"] += 1
        if site_name not in {
            m.get("site_name")
            for m in [meta]
        }:
            stats["sites_found"] += 1
        else:
            stats["sites_found"] += 1

        logger.info(f"  Session: {site_name}  [{timestamp}]  site_id={site_id[:40]}…")

        for abs_path in sorted(session_dir.rglob("*")):
            if not abs_path.is_file():
                continue
            if abs_path.name in _SKIP_FILENAMES:
                continue
            if abs_path.suffix.lower() in _SKIP_SUFFIXES:
                continue

            stats["files_scanned"] += 1

            try:
                checksum      = sha256_file(abs_path)
                stat_info     = abs_path.stat()
                file_size     = stat_info.st_size
                last_modified = datetime.fromtimestamp(stat_info.st_mtime).isoformat()

                # Relative path within this session, e.g. /Documents/Reports/Q1.xlsx
                rel_path = "/" + str(abs_path.relative_to(session_dir)).replace(os.sep, "/")

                logger.debug(f"    {rel_path}  {checksum[:12]}…  {human_size(file_size)}")

                if not dry_run:
                    db.update_file_record(
                        site_id       = site_id,
                        file_path     = rel_path,
                        file_name     = abs_path.name,
                        file_size     = file_size,
                        last_modified = last_modified,
                        checksum      = checksum,
                    )

                stats["files_written"] += 1
                stats["total_bytes"]   += file_size

            except Exception as exc:
                logger.error(f"    Error processing {abs_path}: {exc}")
                stats["files_errors"] += 1

    return stats


# ===========================================================================
# Exchange rebuild
# ===========================================================================

def _session_is_multi_user(session_dir: Path) -> bool:
    """
    Detect whether *session_dir* uses the OLD multi-user layout::

        session_dir / <user_name> / <folder_name> / message.eml

    vs the NEW single-user layout::

        session_dir / <folder_name> / message.eml

    Heuristic: if every direct child directory contains only sub-directories
    (no .eml/.json files immediately inside it), the children are user-name
    directories, not mail-folder directories.  Returns True for old layout.
    """
    has_any_child_dir = False
    for child in session_dir.iterdir():
        if not child.is_dir():
            continue
        has_any_child_dir = True
        # If any child dir contains a direct email file, this child IS a mail
        # folder → new single-user layout.
        for f in child.iterdir():
            if (
                f.is_file()
                and f.suffix.lower() in (".eml", ".json")
                and f.name not in _SKIP_FILENAMES
            ):
                return False
    # Either no child dirs at all (empty session), or none of the child dirs
    # contained email files directly → treat as old multi-user layout.
    return has_any_child_dir


def _collect_messages_from_folder_dir(
    folder_dir: Path,
    messages: Dict[str, Dict[str, Any]],
) -> None:
    """
    Register every .eml / .json file found directly inside *folder_dir*
    into *messages* keyed by filename stem.
    """
    folder_name = folder_dir.name
    for f in folder_dir.iterdir():
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext not in (".eml", ".json"):
            continue
        if f.name in _SKIP_FILENAMES:
            continue
        stem = f.stem
        if stem not in messages:
            messages[stem] = {"eml": None, "json": None, "folder": folder_name}
        messages[stem][ext.lstrip(".")] = f


def rebuild_exchange_db(
    backup_root: Path,
    db_path: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Walk ``<backup_root>/exchange/`` and index every .eml / .json email file
    into the Exchange checksum database.

    Handles two on-disk layouts transparently:

    **New layout** (per-user sessions)::

        exchange/<user>/<timestamp>/<folder>/<files>

    **Old layout** (multi-user "all_users" sessions)::

        exchange/all_users/<timestamp>/<user>/<folder>/<files>

    For each message stem, metadata is extracted preferentially from the
    paired .json file (full Graph API response), falling back to EML header
    parsing.  User email addresses are resolved from ``user_metadata.json``
    where available; a pre-scan builds a ``short_name → email`` map from all
    new-layout sessions so old-layout entries receive correct full emails.
    """
    from exchange_checksum_db import ExchangeChecksumDB     # lazy import

    exchange_dir = backup_root / "exchange"
    if not exchange_dir.is_dir():
        logger.warning(
            f"Exchange backup directory not found: {exchange_dir}\n"
            f"  (pass --backup-dir pointing to the directory that contains 'exchange/')"
        )
        return {}

    stats: Dict[str, Any] = {
        "users_found":      0,
        "sessions_found":   0,
        "messages_scanned": 0,
        "messages_written": 0,
        "messages_skipped": 0,
        "messages_errors":  0,
        "total_bytes":      0,
    }

    db = None if dry_run else ExchangeChecksumDB(db_path)

    # ------------------------------------------------------------------
    # Phase 0 – build short_name → full_email map from all user_metadata.json
    # files found under new-layout sessions.  This allows old-layout sessions
    # (which have no metadata file) to store the correct full email address.
    # ------------------------------------------------------------------
    user_email_map: Dict[str, str] = {}
    for user_dir in exchange_dir.iterdir():
        if not user_dir.is_dir() or user_dir.name == "all_users":
            continue
        for session_dir in user_dir.iterdir():
            meta_path = session_dir / "user_metadata.json"
            if meta_path.is_file():
                try:
                    with open(meta_path, encoding="utf-8") as fh:
                        umeta = json.load(fh)
                    email = (
                        umeta.get("user_email")
                        or umeta.get("userPrincipalName")
                        or umeta.get("mail")
                    )
                    if email:
                        user_email_map[user_dir.name] = email
                        break           # one successful hit per user dir is enough
                except Exception:
                    pass

    logger.debug(f"  User email map from metadata: {user_email_map}")

    # ------------------------------------------------------------------
    # Helper: process one message records dict and write to DB.
    # ------------------------------------------------------------------
    def _write_messages(
        messages: Dict[str, Dict[str, Any]],
        user_email: str,
    ) -> None:
        """Compute checksums for *messages* and upsert into the DB."""
        for stem, info in messages.items():
            json_file    = info["json"]
            eml_file     = info["eml"]
            folder_name  = info["folder"]
            primary_file = json_file or eml_file
            if primary_file is None:
                continue

            stats["messages_scanned"] += 1
            try:
                # Extract metadata
                subject          = ""
                sender           = ""
                received_date    = ""
                message_id       = stem       # fallback
                has_attachments  = False
                attachment_count = 0
                backup_format    = (
                    "both" if (eml_file and json_file)
                    else ("json" if json_file else "eml")
                )

                if json_file and json_file.is_file():
                    try:
                        with open(json_file, encoding="utf-8") as jf:
                            msg_data = json.load(jf)
                        message_id       = msg_data.get("id") or stem
                        subject          = msg_data.get("subject", "")
                        from_block       = msg_data.get("from", {})
                        sender           = from_block.get("emailAddress", {}).get("address", "")
                        received_date    = msg_data.get("receivedDateTime", "")
                        has_attachments  = msg_data.get("hasAttachments", False)
                        attachment_count = len(msg_data.get("attachments", []))
                    except Exception as exc:
                        logger.debug(f"    JSON parse error {json_file.name}: {exc}")

                elif eml_file and eml_file.is_file():
                    hdrs          = parse_eml_headers(eml_file)
                    subject       = hdrs.get("subject", "")
                    sender        = hdrs.get("sender", "")
                    received_date = hdrs.get("received_date", "")
                    _, message_id = extract_msg_id_from_stem(stem)

                checksum    = sha256_file(primary_file)
                file_size   = primary_file.stat().st_size
                backup_path = str(primary_file.parent)

                logger.debug(
                    f"    [{folder_name}] {subject[:55]!r}  "
                    f"{checksum[:12]}…  {human_size(file_size)}"
                )

                if not dry_run:
                    db.update_email_record(
                        user_id          = user_email,
                        message_id       = message_id,
                        folder_id        = None,
                        folder_name      = folder_name,
                        subject          = subject,
                        sender           = sender,
                        received_date    = received_date,
                        message_size     = file_size,
                        checksum         = checksum,
                        has_attachments  = has_attachments,
                        attachment_count = attachment_count,
                        backup_format    = backup_format,
                        backup_path      = backup_path,
                    )

                stats["messages_written"] += 1
                stats["total_bytes"]      += file_size

            except Exception as exc:
                logger.error(f"    Error processing message stem '{stem}': {exc}")
                stats["messages_errors"] += 1

    # ------------------------------------------------------------------
    # Phase 1 – walk user directories.
    # ------------------------------------------------------------------
    for user_dir in sorted(exchange_dir.iterdir()):
        if not user_dir.is_dir():
            continue

        user_name = user_dir.name
        stats["users_found"] += 1
        logger.info(f"  User dir: {user_name}")

        for session_dir in sorted(user_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            if not re.fullmatch(r"\d{8}_\d{6}", session_dir.name):
                continue

            stats["sessions_found"] += 1
            timestamp = session_dir.name

            # ---- Resolve user email for this session ----
            user_email = user_email_map.get(user_name, user_name)

            # Override from user_metadata.json if present (new layout)
            user_meta_path = session_dir / "user_metadata.json"
            if user_meta_path.is_file():
                try:
                    with open(user_meta_path, encoding="utf-8") as fh:
                        umeta = json.load(fh)
                    user_email = (
                        umeta.get("user_email")
                        or umeta.get("userPrincipalName")
                        or umeta.get("mail")
                        or user_email
                    )
                except Exception:
                    pass

            # ---- Detect old vs new layout ----
            multi_user = _session_is_multi_user(session_dir)

            if multi_user:
                # OLD LAYOUT: session/<user_name>/<folder>/<files>
                logger.debug(
                    f"    Session {timestamp}  [multi-user layout]  "
                    f"parent={user_name}"
                )
                for subuser_dir in sorted(session_dir.iterdir()):
                    if not subuser_dir.is_dir():
                        continue
                    subuser_name  = subuser_dir.name
                    subuser_email = user_email_map.get(subuser_name, subuser_name)
                    logger.debug(f"      Sub-user: {subuser_name}  →  {subuser_email}")

                    messages: Dict[str, Dict[str, Any]] = {}
                    for folder_dir in sorted(subuser_dir.iterdir()):
                        if folder_dir.is_dir():
                            _collect_messages_from_folder_dir(folder_dir, messages)
                        elif (
                            folder_dir.is_file()
                            and folder_dir.suffix.lower() in (".eml", ".json")
                            and folder_dir.name not in _SKIP_FILENAMES
                        ):
                            # File directly under the user dir (no folder)
                            stem = folder_dir.stem
                            ext  = folder_dir.suffix.lower().lstrip(".")
                            if stem not in messages:
                                messages[stem] = {"eml": None, "json": None, "folder": "root"}
                            messages[stem][ext] = folder_dir

                    _write_messages(messages, subuser_email)

            else:
                # NEW LAYOUT: session/<folder>/<files>
                logger.debug(
                    f"    Session {timestamp}  [single-user layout]  "
                    f"user={user_email}"
                )
                messages: Dict[str, Dict[str, Any]] = {}
                for child in sorted(session_dir.iterdir()):
                    if child.is_dir():
                        _collect_messages_from_folder_dir(child, messages)
                    elif (
                        child.is_file()
                        and child.suffix.lower() in (".eml", ".json")
                        and child.name not in _SKIP_FILENAMES
                    ):
                        stem = child.stem
                        ext  = child.suffix.lower().lstrip(".")
                        if stem not in messages:
                            messages[stem] = {"eml": None, "json": None, "folder": "root"}
                        messages[stem][ext] = child

                _write_messages(messages, user_email)

    return stats


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rebuild_databases.py",
        description="Rebuild M365 backup checksum databases from disk (no cloud access needed).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--backup-dir", default="backup", metavar="DIR",
        help="Root backup directory (default: backup/)",
    )
    parser.add_argument(
        "--type", choices=["sharepoint", "exchange", "all"], default="all",
        help="Which database to rebuild (default: all)",
    )
    parser.add_argument(
        "--sharepoint-db", default="backup_checksums.db", metavar="FILE",
        help="SharePoint checksum DB path (default: backup_checksums.db)",
    )
    parser.add_argument(
        "--exchange-db", default="backup_checksums_exchange.db", metavar="FILE",
        help="Exchange checksum DB path (default: backup_checksums_exchange.db)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scan and compute checksums but do NOT write to any database",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show per-file debug output",
    )
    parser.add_argument(
        "--log-file", default="rebuild_databases.log", metavar="FILE",
        help="Log file path (default: rebuild_databases.log)",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Logging setup
    # ------------------------------------------------------------------
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers: list = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    except OSError as exc:
        print(f"WARNING: Cannot open log file {args.log_file}: {exc}", file=sys.stderr)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )

    # ------------------------------------------------------------------
    # Validate backup root
    # ------------------------------------------------------------------
    backup_root = Path(args.backup_dir)
    if not backup_root.is_dir():
        logger.error(f"Backup directory not found: {backup_root.resolve()}")
        sys.exit(1)

    if args.dry_run:
        logger.warning("*** DRY RUN – no database writes will occur ***")

    overall_start = datetime.now()
    logger.info(f"Backup root : {backup_root.resolve()}")
    logger.info(f"Rebuild type: {args.type}")
    logger.info(f"Started     : {overall_start:%Y-%m-%d %H:%M:%S}")

    # ==================================================================
    # SharePoint
    # ==================================================================
    if args.type in ("sharepoint", "all"):
        logger.info("")
        logger.info("=" * 70)
        logger.info("SHAREPOINT  –  rebuilding checksum database")
        logger.info(f"  DB path    : {Path(args.sharepoint_db).resolve()}")
        logger.info("=" * 70)

        # Search directly under backup_root AND under backup_root/sharepoint
        # by always using rglob from backup_root (it finds both naturally).
        sp_stats = rebuild_sharepoint_db(
            backup_root  = backup_root,
            db_path      = args.sharepoint_db,
            dry_run      = args.dry_run,
        )

        logger.info("")
        logger.info("SharePoint rebuild summary:")
        for key, val in sp_stats.items():
            display = human_size(val) if key == "total_bytes" else val
            logger.info(f"  {key:<22}: {display}")

    # ==================================================================
    # Exchange
    # ==================================================================
    if args.type in ("exchange", "all"):
        logger.info("")
        logger.info("=" * 70)
        logger.info("EXCHANGE  –  rebuilding checksum database")
        logger.info(f"  DB path    : {Path(args.exchange_db).resolve()}")
        logger.info("=" * 70)

        ex_stats = rebuild_exchange_db(
            backup_root = backup_root,
            db_path     = args.exchange_db,
            dry_run     = args.dry_run,
        )

        logger.info("")
        logger.info("Exchange rebuild summary:")
        for key, val in ex_stats.items():
            display = human_size(val) if key == "total_bytes" else val
            logger.info(f"  {key:<22}: {display}")

    # ==================================================================
    # Done
    # ==================================================================
    duration = datetime.now() - overall_start
    logger.info("")
    logger.info(f"Finished in {duration}  (log → {args.log_file})")


if __name__ == "__main__":
    main()
