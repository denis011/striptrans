import httpx
import pytest
from fastapi.testclient import TestClient
from llama_mock import ocr_server, refused
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import make_engine, run_migrations
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    # testovi ne smeju da zavise od .env-a ni da zovu udaljene modele
    return Settings(
        data_dir=str(tmp_path),
        database_url=f"sqlite:///{tmp_path}/test.db",
        translation_model="or:test/model",
        ocr_server="auto",
        openrouter_api_key="",
    )


def _client(settings: Settings, handler) -> TestClient:
    return TestClient(create_app(settings, llama_transport=httpx.MockTransport(handler)))


@pytest.fixture
def client(settings):
    with _client(settings, ocr_server([], "Nemamo vremena sada.")) as c:
        yield c


@pytest.fixture
def client_llama_down(settings):
    with _client(settings, refused) as c:
        yield c


@pytest.fixture
def session_factory(settings):
    run_migrations(settings.database_url)
    engine = make_engine(settings.database_url)
    yield sessionmaker(engine)
    engine.dispose()


@pytest.fixture
def make_client(settings):
    """Pravi test klijent sa zadatim mock llama-server handler-om."""
    clients = []

    def factory(handler):
        client = _client(settings, handler)
        clients.append(client)
        return client.__enter__()

    yield factory
    for client in clients:
        client.__exit__(None, None, None)
