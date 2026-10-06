from datetime import UTC, datetime

import pytest

from custom_components.wolkenwart_regenradar.radar import (
    MAX_DOWNLOAD,
    RadarError,
    download,
)

T = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


class Response:
    def __init__(self, status=200, length=None, chunks=(b"abc", b"def")):
        self.status = status
        self.content_length = length
        self.chunks = chunks
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def iter_chunked(self, size):
        for chunk in self.chunks:
            yield chunk


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **options):
        self.calls.append((url, options))
        return self.response


async def test_request_target_redirects_timeout_and_stream():
    s = Session(Response())
    assert await download(s, T) == b"abcdef"
    url, options = s.calls[0]
    assert (
        url
        == "https://opendata.dwd.de/weather/radar/composite/rv/composite_rv_20261006_1200.tar"
    )
    assert options["allow_redirects"] is False and options["timeout"].total == 45


@pytest.mark.parametrize("status", [301, 404, 429, 500, 503])
async def test_http_errors_are_never_data(status):
    with pytest.raises(RadarError, match=str(status)):
        await download(Session(Response(status)), T)


async def test_declared_size_limit():
    with pytest.raises(RadarError, match="too large"):
        await download(Session(Response(length=MAX_DOWNLOAD + 1)), T)


async def test_streamed_size_limit(monkeypatch):
    monkeypatch.setattr("custom_components.wolkenwart_regenradar.radar.MAX_DOWNLOAD", 5)
    with pytest.raises(RadarError, match="too large"):
        await download(Session(Response()), T)
