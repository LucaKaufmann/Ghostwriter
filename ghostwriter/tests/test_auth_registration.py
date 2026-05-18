"""Tests for auth registration."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.api import auth as auth_api
from app.models.user import User, UserCreate


def test_concurrent_first_registration_creates_only_one_admin(
    tmp_path,
    monkeypatch,
):
    """Concurrent setup attempts should serialize and create one admin."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    first_hash_started = threading.Event()
    second_attempt_started = threading.Event()
    release_first_hash = threading.Event()
    hash_lock = threading.Lock()
    hash_calls = 0

    def slow_first_hash(password: str) -> str:
        nonlocal hash_calls
        with hash_lock:
            hash_calls += 1
            call_number = hash_calls
        if call_number == 1:
            first_hash_started.set()
            assert release_first_hash.wait(timeout=5)
        return f"hashed:{password}"

    monkeypatch.setattr(auth_api, "hash_password", slow_first_hash)

    def register_user(username: str) -> tuple[int, str] | tuple[str, bool]:
        if username == "second-admin":
            second_attempt_started.set()
        with Session(engine) as session:
            try:
                response = asyncio.run(
                    auth_api.register(
                        UserCreate(username=username, password="password-123"),
                        request=None,
                        session=session,
                    )
                )
            except HTTPException as exc:
                return exc.status_code, exc.detail
            return response.user.username, response.user.is_admin

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(register_user, "first-admin")
        assert first_hash_started.wait(timeout=5)

        second = executor.submit(register_user, "second-admin")
        assert second_attempt_started.wait(timeout=5)
        time.sleep(0.1)
        release_first_hash.set()

        results = [first.result(timeout=5), second.result(timeout=5)]

    assert sum(result[1] is True for result in results) == 1
    assert sum(result[0] == 403 for result in results) == 1

    with Session(engine) as session:
        users = session.exec(select(User)).all()

    assert len(users) == 1
    assert users[0].is_admin is True
