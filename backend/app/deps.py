from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.services.llamaserver import LlamaServerClient


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def _llama(request: Request) -> LlamaServerClient:
    return request.app.state.llama


SettingsDep = Annotated[Settings, Depends(_settings)]
SessionDep = Annotated[Session, Depends(_session)]
LlamaDep = Annotated[LlamaServerClient, Depends(_llama)]
