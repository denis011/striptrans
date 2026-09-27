import io
from pathlib import Path

import pytest
from factories import jpeg_bytes, zip_bytes
from sqlalchemy import select

from app.jobs import recover_interrupted_jobs
from app.models import Job, Page, Project
from app.services.page_import import queue_import
from worker.main import run_once


@pytest.fixture
def project_id(session_factory):
    with session_factory() as session:
        project = Project(series_id=1, issue_number="12")
        session.add(project)
        session.commit()
        return project.id


def import_files(session_factory, settings, project_id, files, kind="original") -> Job:
    streams = [(name, io.BytesIO(data)) for name, data in files]
    with session_factory() as session:
        job_id = queue_import(session, settings.data_dir, project_id, kind, streams).id
    run_once(session_factory, "w1", settings)
    with session_factory() as session:
        return session.get(Job, job_id)


def project_files(settings, project_id) -> list[Path]:
    root = Path(settings.data_dir, "projects", str(project_id))
    return [path for path in root.rglob("*") if path.is_file()]


def uploads(settings) -> list[Path]:
    return list(Path(settings.data_dir, "uploads").iterdir())


def test_import_skips_non_images_and_removes_upload(session_factory, settings, project_id):
    archive = zip_bytes(
        [("2.jpg", jpeg_bytes()), ("ComicInfo.xml", b"<ComicInfo/>"), ("1.jpg", jpeg_bytes())]
    )

    job = import_files(session_factory, settings, project_id, [("z.cbz", archive)])

    assert job.status == "done", job.error
    assert job.result == {"pages": 2, "skipped": ["z.cbz/ComicInfo.xml"]}
    assert (job.progress, job.total) == (3, 3)
    assert len(project_files(settings, project_id)) == 4  # 2 slike + 2 sličice
    assert uploads(settings) == []


def test_next_import_appends_after_existing_pages(session_factory, settings, project_id):
    import_files(session_factory, settings, project_id, [("a.jpg", jpeg_bytes())])
    import_files(session_factory, settings, project_id, [("b.jpg", jpeg_bytes())])

    with session_factory() as session:
        pages = session.scalars(select(Page).order_by(Page.position)).all()
        assert [(p.source_name, p.position) for p in pages] == [("a.jpg", 1), ("b.jpg", 2)]


def test_archive_without_images_fails_cleanly(session_factory, settings, project_id):
    archive = zip_bytes([("readme.txt", b"zdravo")])

    job = import_files(session_factory, settings, project_id, [("x.zip", archive)])

    assert job.status == "failed"
    assert "nijedna slika" in job.error
    assert project_files(settings, project_id) == []
    assert uploads(settings) == []


def test_failure_midway_removes_already_imported_pages(session_factory, settings, project_id):
    broken = jpeg_bytes(size=(400, 400), noise=True)
    archive = zip_bytes([("1.jpg", jpeg_bytes()), ("2.jpg", broken[: len(broken) // 2])])

    job = import_files(session_factory, settings, project_id, [("x.cbz", archive)])

    assert job.status == "failed"
    assert "oštećena" in job.error
    with session_factory() as session:
        assert session.scalars(select(Page)).all() == []
    assert project_files(settings, project_id) == []


def test_archive_names_never_become_paths(session_factory, settings, project_id):
    archive = zip_bytes([("../../evil.jpg", jpeg_bytes()), ("001.jpg", jpeg_bytes())])

    job = import_files(session_factory, settings, project_id, [("x.cbz", archive)])

    assert job.result["pages"] == 1
    assert list(Path(settings.data_dir).parent.rglob("evil.jpg")) == []


def test_interrupted_import_is_failed_and_cleaned_up(session_factory, settings, project_id):
    with session_factory() as session:
        files = [("a.jpg", io.BytesIO(jpeg_bytes()))]
        job = queue_import(session, settings.data_dir, project_id, "original", files)
        job.status = "running"
        session.commit()

        assert recover_interrupted_jobs(session, Path(settings.data_dir)) == 1
        assert job.status == "failed"
    assert uploads(settings) == []
