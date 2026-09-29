"""Putanje fajlova sastavljene od podataka iz zahteva moraju da ostanu unutar svog foldera."""

import os
from pathlib import Path


class UnsafePath(ValueError):
    """Putanja bi izašla van dozvoljenog foldera."""


def inside(base: Path, *parts: str | int) -> Path:
    """`base/parts…`, normalizovano; greška ako rezultat nije unutar `base` (npr. „../")."""
    root = os.path.normpath(os.fspath(base))
    target = os.path.normpath(os.path.join(root, *(str(part) for part in parts)))
    if not target.startswith(root + os.sep):
        raise UnsafePath(f"putanja van foldera: {target}")
    return Path(target)
