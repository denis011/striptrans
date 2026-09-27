import io
import zipfile

from PIL import Image


def jpeg_bytes(size=(60, 90), value=128, noise=False) -> bytes:
    image = Image.effect_noise(size, 60) if noise else Image.new("L", size, value)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def zip_bytes(entries) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def create_page(client, size=(600, 800), series_id=1, noise=False) -> dict:
    """Projekat sa jednom uvezenom stranicom date veličine; vraća stranicu iz API-ja."""
    from worker.main import run_once

    project = client.post("/api/projects", json={"series_id": series_id}).json()
    archive = zip_bytes([("1.jpg", jpeg_bytes(size=size, noise=noise))])
    client.post(
        f"/api/projects/{project['id']}/imports",
        data={"kind": "original"},
        files=[("files", ("a.cbz", archive, "application/zip"))],
    )
    state = client.app.state
    run_once(state.session_factory, "w1", state.settings)
    return client.get(f"/api/projects/{project['id']}/pages").json()[0]
