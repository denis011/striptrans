"""Putanje fajlova sastavljene od podataka iz zahteva moraju da ostanu unutar svog foldera."""

import os
from pathlib import Path

from PIL import Image


class UnsafePath(ValueError):
    """Putanja bi izašla van dozvoljenog foldera."""


def inside(base: Path, *parts: str | int) -> Path:
    """`base/parts…`, normalizovano; greška ako rezultat nije unutar `base` (npr. „../")."""
    root = os.path.normpath(os.fspath(base))
    target = os.path.normpath(os.path.join(root, *(str(part) for part in parts)))
    if not target.startswith(root + os.sep):
        raise UnsafePath(f"putanja van foldera: {target}")
    return Path(target)


def save_atomic(image: Image.Image, target: Path, **options) -> None:
    """Upiši sliku preko stare tek kad je cela: prekinut upis (gašenje Dockera) je ne kvari."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.tmp")
    try:
        image.save(temporary, Image.registered_extensions()[target.suffix.lower()], **options)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
