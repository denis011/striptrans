from app.models import Job, WorkerHeartbeat
from worker.main import run_once


def add_job(session_factory, **fields) -> int:
    with session_factory() as session:
        job = Job(**fields)
        session.add(job)
        session.commit()
        return job.id


def test_idle_worker_sends_heartbeat(session_factory, settings):
    assert run_once(session_factory, "w1", settings) is False
    with session_factory() as session:
        assert session.get(WorkerHeartbeat, "w1") is not None


def test_processes_ping_job(session_factory, settings):
    job_id = add_job(session_factory, type="ping", payload={"x": 1})

    assert run_once(session_factory, "w1", settings) is True

    with session_factory() as session:
        job = session.get(Job, job_id)
        assert job.status == "done"
        assert job.result == {"pong": True, "x": 1}


def test_unknown_job_type_fails_with_error(session_factory, settings):
    job_id = add_job(session_factory, type="nepostojeci")

    run_once(session_factory, "w1", settings)

    with session_factory() as session:
        job = session.get(Job, job_id)
        assert job.status == "failed"
        assert "nepostojeci" in job.error


def test_running_jobs_are_not_claimed_again(session_factory, settings):
    add_job(session_factory, type="ping", status="running")

    assert run_once(session_factory, "w1", settings) is False
