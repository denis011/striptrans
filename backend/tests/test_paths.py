import pytest
from PIL import Image

from app.paths import save_atomic


def test_interrupted_save_keeps_the_old_image(tmp_path, monkeypatch):
    target = tmp_path / "clean" / "1.png"
    save_atomic(Image.new("L", (20, 10), 50), target)

    def broken(self, path, *args, **kwargs):
        open(path, "wb").write(b"pola fajla")  # upis prekinut usred posla
        raise OSError("disk je pun")

    monkeypatch.setattr(Image.Image, "save", broken)
    with pytest.raises(OSError):
        save_atomic(Image.new("L", (20, 10), 200), target)
    monkeypatch.undo()

    with Image.open(target) as image:
        assert image.getpixel((0, 0)) == 50  # stara slika je cela
    assert [path.name for path in target.parent.iterdir()] == ["1.png"]  # bez .tmp ostatka
