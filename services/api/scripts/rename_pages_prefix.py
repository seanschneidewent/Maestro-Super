"""
One-time script to rename multi-page PDF pages from suffix to prefix format.

Changes names from: "Name (1 of 3)" -> "(1 of 3) Name"

Usage:
    cd services/api
    python -m scripts.rename_pages_prefix [--dry-run]

Options:
    --dry-run       Show what would be changed without making changes
"""

import argparse
import re
import sys
from pathlib import Path

# Add the api directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.session import SessionLocal
from app.models.page import Page


# Pattern to match old format: "Name (X of Y)" where X and Y are numbers
OLD_FORMAT_PATTERN = re.compile(r'^(.+) \((\d+) of (\d+)\)$')


def main():
    parser = argparse.ArgumentParser(
        description="Rename multi-page PDF pages from suffix to prefix format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Multi-Page PDF Rename Script (Suffix -> Prefix)")
    print("=" * 60)

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")

    db = SessionLocal()

    try:
        # Find all pages with old format (ends with "(X of Y)")
        pages = db.query(Page).all()

        pages_to_rename = []
        for page in pages:
            match = OLD_FORMAT_PATTERN.match(page.page_name)
            if match:
                pages_to_rename.append({
                    'page': page,
                    'base_name': match.group(1),
                    'current_num': match.group(2),
                    'total_num': match.group(3),
                })

        print(f"\nFound {len(pages_to_rename)} pages with old format")

        if not pages_to_rename:
            print("No pages need renaming.")
            return 0

        renamed_count = 0
        for item in pages_to_rename:
            page = item['page']
            old_name = page.page_name
            new_name = f"({item['current_num']} of {item['total_num']}) {item['base_name']}"

            if args.dry_run:
                print(f"  [DRY RUN] Would rename: {old_name}")
                print(f"             ->         : {new_name}")
            else:
                page.page_name = new_name
                print(f"  Renamed: {old_name}")
                print(f"       ->: {new_name}")
                renamed_count += 1

        if not args.dry_run:
            print("-" * 40)
            print("Committing changes...")
            db.commit()
            print("Changes committed successfully!")

        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Pages renamed: {renamed_count if not args.dry_run else 0} (would rename: {len(pages_to_rename)})")

        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
