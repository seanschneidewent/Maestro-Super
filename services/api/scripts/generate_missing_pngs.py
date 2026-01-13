"""
One-time script to generate PNGs for pages that are missing them.

This is used after migrating multi-page PDFs to generate PNGs for the
newly created page records.

Usage:
    cd services/api
    python -m scripts.generate_missing_pngs [--dry-run] [--project-id UUID]

Options:
    --dry-run       Show what would be generated without actually generating
    --project-id    Only process a specific project (default: all projects)
"""

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

# Add the api directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.session import SessionLocal
from app.models.page import Page
from app.models.discipline import Discipline
from app.services.storage import download_file, upload_page_image
from app.services.pdf_renderer import pdf_page_to_image


async def generate_png_for_page(page_id: str, project_id: str, pdf_bytes: bytes, page_index: int) -> tuple[bool, str | None]:
    """Generate PNG for a single page and upload to storage."""
    try:
        # Render the specific page
        png_bytes = pdf_page_to_image(pdf_bytes, page_index, dpi=150)

        # Upload to storage
        storage_path = await upload_page_image(png_bytes, project_id, page_id)

        return True, storage_path
    except Exception as e:
        return False, str(e)


async def main():
    parser = argparse.ArgumentParser(
        description="Generate PNGs for pages that are missing them"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without actually generating",
    )
    parser.add_argument(
        "--project-id",
        type=str,
        help="Only process a specific project (default: all projects)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Generate Missing PNGs Script")
    print("=" * 60)

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")

    db = SessionLocal()

    try:
        # Find all pages needing PNG generation
        query = db.query(Page).filter(Page.page_image_ready == False)

        if args.project_id:
            # Filter by project
            query = query.join(Discipline).filter(Discipline.project_id == args.project_id)

        pages = query.all()

        print(f"\nFound {len(pages)} pages needing PNG generation")

        if not pages:
            print("No pages need PNG generation.")
            return 0

        # Group pages by file_path to avoid re-downloading same PDF
        pages_by_path: dict[str, list[Page]] = defaultdict(list)
        for page in pages:
            pages_by_path[page.file_path].append(page)

        print(f"Unique PDFs to download: {len(pages_by_path)}")

        stats = {
            'pdfs_downloaded': 0,
            'pngs_generated': 0,
            'errors': [],
        }

        for file_path, pages_list in pages_by_path.items():
            print(f"\nProcessing: {file_path}")
            print(f"  Pages to generate: {len(pages_list)}")

            if args.dry_run:
                for page in pages_list:
                    print(f"  [DRY RUN] Would generate PNG for: {page.page_name} (page_index={page.page_index})")
                continue

            try:
                # Download the PDF once
                pdf_bytes = await download_file(file_path)
                stats['pdfs_downloaded'] += 1
                print(f"  Downloaded PDF ({len(pdf_bytes)} bytes)")

                # Get project_id from the first page's discipline
                disc = db.query(Discipline).filter(Discipline.id == pages_list[0].discipline_id).first()
                if not disc:
                    print(f"  ERROR: Could not find discipline for page")
                    stats['errors'].append(f"No discipline for {file_path}")
                    continue

                project_id = str(disc.project_id)

                # Generate PNG for each page
                for page in pages_list:
                    success, result = await generate_png_for_page(
                        str(page.id),
                        project_id,
                        pdf_bytes,
                        page.page_index,
                    )

                    if success:
                        # Update database
                        page.page_image_path = result
                        page.page_image_ready = True
                        stats['pngs_generated'] += 1
                        print(f"  Generated: {page.page_name} -> {result}")
                    else:
                        stats['errors'].append(f"{page.page_name}: {result}")
                        print(f"  ERROR: {page.page_name}: {result}")

            except Exception as e:
                error_msg = f"Error downloading {file_path}: {e}"
                print(f"  {error_msg}")
                stats['errors'].append(error_msg)

        # Commit changes
        if not args.dry_run:
            print("-" * 40)
            print("Committing changes...")
            db.commit()
            print("Changes committed successfully!")

        # Summary
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"PDFs downloaded:   {stats['pdfs_downloaded']}")
        print(f"PNGs generated:    {stats['pngs_generated']}")
        print(f"Errors:            {len(stats['errors'])}")

        if stats['errors']:
            print("\nErrors encountered:")
            for error in stats['errors']:
                print(f"  - {error}")

        return 0 if not stats['errors'] else 1

    finally:
        db.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
