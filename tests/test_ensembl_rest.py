"""Ensembl REST client: retry with backoff around the bulk lookup POST."""

from __future__ import annotations

from collections.abc import Callable

import pytest
import requests

from hustring.errors import MappingError
from hustring.mapping import ensembl_rest


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self.payload


def _post_sequence(
    failures: int, payload: object
) -> tuple[Callable[..., FakeResponse], list[int]]:
    calls: list[int] = []

    def post(*_args: object, **_kwargs: object) -> FakeResponse:
        calls.append(1)
        if len(calls) <= failures:
            raise requests.exceptions.ConnectionError("connection reset")
        return FakeResponse(payload)

    return post, calls


def test_lookup_retries_transient_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    post, calls = _post_sequence(2, {"ENSG1": {"display_name": "TP53"}})
    sleeps: list[float] = []
    monkeypatch.setattr(ensembl_rest.requests, "post", post)
    monkeypatch.setattr(ensembl_rest.time, "sleep", sleeps.append)

    client = ensembl_rest.EnsemblRestClient()
    assert client.lookup_ids(["ENSG1"]) == {"ENSG1": {"display_name": "TP53"}}
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


def test_lookup_gives_up_after_three_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    post, calls = _post_sequence(10, {})
    sleeps: list[float] = []
    monkeypatch.setattr(ensembl_rest.requests, "post", post)
    monkeypatch.setattr(ensembl_rest.time, "sleep", sleeps.append)

    client = ensembl_rest.EnsemblRestClient()
    with pytest.raises(MappingError, match="request failed"):
        client.lookup_ids(["ENSG1"])
    assert len(calls) == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_lookup_retries_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadJson(FakeResponse):
        def json(self) -> object:
            raise ValueError("Expecting value")

    calls: list[int] = []

    def post(*_args: object, **_kwargs: object) -> FakeResponse:
        calls.append(1)
        if len(calls) == 1:
            return BadJson({})
        return FakeResponse({"ENSG1": {"display_name": "TP53"}})

    sleeps: list[float] = []
    monkeypatch.setattr(ensembl_rest.requests, "post", post)
    monkeypatch.setattr(ensembl_rest.time, "sleep", sleeps.append)

    client = ensembl_rest.EnsemblRestClient()
    assert client.lookup_ids(["ENSG1"]) == {"ENSG1": {"display_name": "TP53"}}
    assert len(calls) == 2
    assert sleeps == [1.0]


def test_lookup_does_not_retry_unexpected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    post, calls = _post_sequence(0, ["unexpected"])
    sleeps: list[float] = []
    monkeypatch.setattr(ensembl_rest.requests, "post", post)
    monkeypatch.setattr(ensembl_rest.time, "sleep", sleeps.append)

    client = ensembl_rest.EnsemblRestClient()
    with pytest.raises(MappingError, match="unexpected payload"):
        client.lookup_ids(["ENSG1"])
    assert len(calls) == 1
    assert sleeps == []


def test_lookup_skips_empty_input(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*_args: object, **_kwargs: object) -> FakeResponse:
        raise AssertionError("no request expected")

    monkeypatch.setattr(ensembl_rest.requests, "post", post)
    assert ensembl_rest.EnsemblRestClient().lookup_ids([]) == {}
