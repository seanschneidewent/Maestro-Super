"""
One-time migration script to split existing multi-page PDFs.

This script finds all pages with page_index=0, downloads the associated PDFs,
and creates additional Page records for any multi-page PDFs.

Usage:
    cd services/api
    python -m scripts.migrate_multipage_pdfs [--dry-run] [--project-id UUID]

Options:
    --dry-run       Show what would be changed without making changes
    --project-id    Migrate only a specific project (default: all projects)
"""

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from pathlib import Path

# Add the api directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.session import SessionLocal
from app.models.page import Page
from app.models.discipline import Discipline
from app.models.project import Project
from app.services.storage import download_file
from app.services.pdf_renderer import get_pdf_page_count

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def migrate_project(db, project_id: str, dry_run: bool) -> dict:
    """
    Migrate all multi-page PDFs in a project.

    Returns dict with migration stats.
    """
    stats = {
        "pages_checked": 0,
        "pdfs_downloaded": 0,
        "multipage_pdfs": 0,
        "pages_created": 0,
        "pages_renamed": 0,
        "errors": [],
    }

    # Get all pages in this project with page_index=0
    pages = (
        db.query(Page)
        .join(Discipline)
        .filter(
            Discipline.project_id == project_id,
            Page.page_index == 0,
        )
        .all()
    )

    if not pages:
        logger.info(f"No pages found in project {project_id}")
        return stats

    stats["pages_checked"] = len(pages)
    logger.info(f"Found {len(pages)} pages to check in project {project_id}")

    # Group pages by file_path to avoid re-downloading same PDF
    pages_by_path: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        pages_by_path[page.file_path].append(page)

    logger.info(f"Unique PDFs to download: {len(pages_by_path)}")

    # Process each unique PDF
    for file_path, pages_list in pages_by_path.items():
        try:
            # Download PDF
            logger.info(f"Downloading: {file_path}")
            pdf_bytes = await download_file(file_path)
            stats["pdfs_downloaded"] += 1

            # Count pages
            page_count = get_pdf_page_count(pdf_bytes)
            logger.info(f"  Page count: {page_count}")

            if page_count <= 1:
                # Single page PDF, nothing to do
                continue

            stats["multipage_pdfs"] += 1

            # This is a multi-page PDF - need to split
            # Each entry in pages_list is an existing Page record pointing to this PDF
            # (Usually just one, but could be multiple if user uploaded same PDF multiple times)
            for original_page in pages_list:
                base_name = original_page.page_name

                # Check if already migrated (name already has "(X of Y)" format)
                if " of " in base_name and base_name.endswith(")"):
                    logger.info(f"  Skipping already migrated: {base_name}")
                    continue

                new_name = f"{base_name} (1 of {page_count})"

                if dry_run:
                    logger.info(f"  [DRY RUN] Would rename: {base_name} -> {new_name}")
                    logger.info(f"  [DRY RUN] Would create {page_count - 1} additional pages")
                else:
                    # Update original page name
                    original_page.page_name = new_name
                    stats["pages_renamed"] += 1
                    logger.info(f"  Renamed: {base_name} -> {new_name}")

                    # Create additional pages for indices 1..page_count-1
                    for idx in range(1, page_count):
                        new_page = Page(
                            discipline_id=original_page.discipline_id,
                            page_name=f"{base_name} ({idx + 1} of {page_count})",
                            file_path=file_path,
                            page_index=idx,
                        )
                        db.add(new_page)
                        stats["pages_created"] += 1
                        logger.info(f"  Created: {new_page.page_name} (page_index={idx})")

        except Exception as e:
            error_msg = f"Error processing {file_path}: {e}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)

    return stats


async def main():
    parser = argparse.ArgumentParser(
        description="Migrate existing multi-page PDFs to split format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes",
    )
    parser.add_argument(
        "--project-id",
        type=str,
        help="Migrate only a specific project (default: all projects)",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Multi-Page PDF Migration Script")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")

    db = SessionLocal()

    try:
        # Get projects to process
        if args.project_id:
            projects = db.query(Project).filter(Project.id == args.project_id).all()
            if not projects:
                logger.error(f"Project not found: {args.project_id}")
                return 1
        else:
            projects = db.query(Project).all()

        logger.info(f"Projects to process: {len(projects)}")

        total_stats = {
            "pages_checked": 0,
            "pdfs_downloaded": 0,
            "multipage_pdfs": 0,
            "pages_created": 0,
            "pages_renamed": 0,
            "errors": [],
        }

        for project in projects:
            logger.info("-" * 40)
            logger.info(f"Processing project: {project.name} ({project.id})")

            stats = await migrate_project(db, str(project.id), args.dry_run)

            # Accumulate stats
            for key in ["pages_checked", "pdfs_downloaded", "multipage_pdfs", "pages_created", "pages_renamed"]:
                total_stats[key] += stats[key]
            total_stats["errors"].extend(stats["errors"])

        # Commit if not dry run
        if not args.dry_run:
            logger.info("-" * 40)
            logger.info("Committing changes...")
            db.commit()
            logger.info("Changes committed successfully!")

        # Summary
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Pages checked:      {total_stats['pages_checked']}")
        logger.info(f"PDFs downloaded:    {total_stats['pdfs_downloaded']}")
        logger.info(f"Multi-page PDFs:    {total_stats['multipage_pdfs']}")
        logger.info(f"Pages renamed:      {total_stats['pages_renamed']}")
        logger.info(f"Pages created:      {total_stats['pages_created']}")
        logger.info(f"Errors:             {len(total_stats['errors'])}")

        if total_stats["errors"]:
            logger.warning("Errors encountered:")
            for error in total_stats["errors"]:
                logger.warning(f"  - {error}")

        return 0 if not total_stats["errors"] else 1

    finally:
        db.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
