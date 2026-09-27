"""Ponovo izmeri oblike oblačića iz već očišćenih strana (posle promene pravila merenja).

  python -m tools.reshape --project 2 [--dry-run]

Isto radi i dugme „Ponovo izmeri oblačiće" na strani projekta (posao `reshape_project`); alat je
zgodan za `--dry-run`, kad se samo gleda šta bi se promenilo.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import make_engine
from app.models import Page
from app.services.cleaning import CLEAN_KINDS, bubble_shape, remeasure_shapes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", help="samo prikaži šta bi se promenilo")
    args = parser.parse_args()
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    changed = pages_changed = 0
    with sessionmaker(make_engine(settings.database_url))() as session:
        pages = session.scalars(
            select(Page).where(
                Page.project_id == args.project,
                Page.kind == "original",
                Page.clean_path.is_not(None),
            )
        ).all()
        for page in sorted(pages, key=lambda item: item.position):
            if args.dry_run:
                blocks = [block for block in page.blocks if block.kind in CLEAN_KINDS]
                if not blocks:
                    continue
                with Image.open(data_dir / page.clean_path) as image:
                    gray = np.asarray(image.convert("L"))
                count = sum(
                    bubble_shape(gray, (block.x, block.y, block.width, block.height))
                    != block.bubble_polygon
                    for block in blocks
                )
            else:
                count = remeasure_shapes(session, settings, page)
            if count:
                pages_changed += 1
                changed += count
                print(f"strana {page.position}: {count} oblika")
    kako = "bilo bi promenjeno" if args.dry_run else "promenjeno"
    print(f"{kako}: {changed} oblika na {pages_changed} strana")


if __name__ == "__main__":
    main()
