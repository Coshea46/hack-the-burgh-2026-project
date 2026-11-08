"""Real provider parsing/cache/HTTP contracts tested without external requests."""

import asyncio
import copy
import json
import threading
from urllib.parse import parse_qs, urlsplit

import pytest

from backend.football_platform import PlatformHTTPServer, PlatformService
from backend.football_platform.catalog import (
    COMPETITIONS,
    DEFAULT_COMPETITION_CODES,
    search_catalog,
    team_aliases,
)
from backend.football_platform.providers import (
    JSONTransport,
    ProviderError,
    news_payload,
    standings_payload,
)


class Clock:
    def __init__(self):
        self.now = 1700000000.0

    def __call__(self):
        return self.now


def standing(code="PL", *, names=("Arsenal FC", "Chelsea FC")):
    return {"competition": {"code": code, "name": COMPETITIONS[code]["name"], "type": "LEAGUE"},
            "season": {"id": 123, "startDate": "2026-08-01", "endDate": "2027-05-31", "currentMatchday": 12},
            "standings": [{"type": "TOTAL", "stage": "REGULAR_SEASON", "group": None,
                           "table": [{"position": index, "team": {"id": 50 + index, "name": name,
                                                                 "shortName": name.removesuffix(" FC"), "tla": None},
                                      "playedGames": 10, "won": 6, "draw": 2, "lost": 2,
                                      "goalsFor": 20, "goalsAgainst": 10, "goalDifference": 10,
                                      "points": 20, "form": None} for index, name in enumerate(names, 1)]}]}


def story(identifier="football/2026/nov/08/example", *, date="2026-11-08T12:00:00Z", title="Original headline"):
    return {"id": identifier, "sectionId": "football", "webTitle": title,
            "webUrl": "https://www.theguardian.com/" + identifier, "webPublicationDate": date,
            "fields": {"byline": "Original Byline", "copyright": "Guardian News & Media Limited",
                       "body": "Never expose article body", "thumbnail": "https://example.com/image.jpg",
                       "trailText": "Never expose an unlicensed excerpt"}}


def news(*items):
    return {"response": {"status": "ok", "results": list(items or (story(),))}}


class Transport:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.block = None

    def get(self, provider, path, params, headers):
        self.calls.append((provider, path, copy.deepcopy(params), copy.deepcopy(headers)))
        if self.block:
            assert self.block.wait(2)
        if self.failure:
            raise self.failure
        if provider == "guardian":
            return news()
        return standing(path.split("/")[1])


def run(coroutine):
    return asyncio.run(coroutine)


def test_missing_keys_are_honest_and_never_attempt_http_even_for_full_catalog():
    async def check():
        transport = Transport()
        service = PlatformService(transport=transport)
        try:
            table, articles, catalog = await asyncio.gather(service.standings(), service.news(),
                                                           service.catalog(load_teams=True))
            assert table["status"] == articles["status"] == "missing_key"
            assert table["tables"] == articles["articles"] == []
            assert table["fetched_at"] is articles["fetched_at"] is None
            assert catalog["team_catalog_status"] == "missing_key" and catalog["teams"] == []
            assert len([item for item in catalog["competitions"] if item["default"]]) == 8
            assert transport.calls == []
        finally:
            await service.close()
    run(check())


def test_eight_defaults_and_natural_fuzzy_competition_search():
    assert list(DEFAULT_COMPETITION_CODES) == ["PL", "PD", "BL1", "SA", "FL1", "ELC", "DED", "PPL"]
    for query in ("EPL", "Where is the Premier League table?", "premier leage", "English top division"):
        result, ambiguous = search_catalog(query, list(COMPETITIONS.values()), [])
        assert result[0]["competition_code"] == "PL" and not ambiguous


def test_current_club_membership_only_from_provider_and_ambiguous_city_search():
    async def check():
        transport = Transport()
        service = PlatformService(football_key="test-only-football", transport=transport)
        try:
            assert (await service.catalog("Chelsea"))["teams"] == []
            await service.standings("PL")
            catalog = await service.catalog("Show me Chelsea's league")
            assert catalog["matches"][0]["team_name"] == "Chelsea FC"
            assert catalog["matches"][0]["competition_code"] == "PL"
            assert (await service.catalog("Show me Chelsea’s league"))["matches"][0]["team_name"] == "Chelsea FC"
            assert catalog["team_catalog_status"] == "partial"
            assert len(transport.calls) == 1
        finally:
            await service.close()
    run(check())
    teams = [{"id": index, "name": name, "competition_code": "PL",
              "aliases": team_aliases({"name": name})} for index, name in enumerate(
                  ("Manchester City FC", "Manchester United FC"), 1)]
    matches, ambiguous = search_catalog("Manchester", [], teams)
    assert ambiguous and {item["team_id"] for item in matches} == {1, 2}
    exact, ambiguous = search_catalog("man utd", [], teams)
    assert not ambiguous and exact[0]["team_id"] == 2
    assert "bayern munich" in team_aliases({"name": "FC Bayern München"})


def test_standings_preserve_group_format_null_unknown_stats_and_deductions():
    payload = standing()
    first = payload["standings"][0]["table"][0]
    first.update(playedGames=None, points=-2, goalDifference=-10)
    payload["standings"][0].update(stage="GROUP_STAGE", group="GROUP_A")
    second = copy.deepcopy(payload["standings"][0])
    second["group"] = "GROUP_B"
    payload["standings"].append(second)
    result = standings_payload(payload, "PL")
    assert [table["group"] for table in result["tables"]] == ["GROUP_A", "GROUP_B"]
    row = result["tables"][0]["rows"][0]
    assert row["played"] is None and row["form"] is None
    assert row["points"] == -2 and row["goal_difference"] == -10
    assert result["season"]["start_date"] == "2026-08-01"


@pytest.mark.parametrize("mutation", [
    lambda data: data["competition"].update(code="PD"),
    lambda data: data["standings"][0]["table"][0].update(points=True),
    lambda data: data["standings"][0]["table"][0].update(points=float("nan")),
    lambda data: data["standings"][0]["table"].append(copy.deepcopy(data["standings"][0]["table"][0])),
])
def test_malformed_provider_standings_rejected(mutation):
    payload = standing()
    mutation(payload)
    with pytest.raises(ProviderError):
        standings_payload(payload, "PL")


def test_news_metadata_original_attribution_sort_dedupe_and_safe_publisher_links():
    older = story(date="2026-11-07T11:00:00Z")
    newer = story("football/2026/nov/08/new", title="Unchanged full headline")
    unsafe = story("football/unsafe")
    unsafe["webUrl"] = "https://attacker.example/other"
    unrelated = story("world/unrelated")
    unrelated["sectionId"] = "world"
    result = news_payload(news(older, newer, older, unsafe, unrelated))
    assert [item["title"] for item in result["articles"]] == ["Unchanged full headline", "Original headline"]
    article = result["articles"][0]
    assert article["byline"] == "Original Byline" and article["copyright"] == "Guardian News & Media Limited"
    assert article["image_url"] is article["excerpt"] is None
    assert "Never expose" not in json.dumps(result)


@pytest.mark.parametrize("date", ["yesterday", "2026-11-08T12:00:00", "", "9999999999999"])
def test_news_requires_real_timezone_aware_publication_timestamp(date):
    with pytest.raises(ProviderError):
        news_payload(news(story(date=date)))


def test_provider_auth_fixed_hosts_no_redirect_and_bounded_read(monkeypatch):
    from backend.football_platform import providers

    captured = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, bound):
            assert bound == JSONTransport.MAX_BYTES + 1
            return b'{"response":{"status":"ok","results":[]}}'

    class Opener:
        def open(self, req, timeout):
            assert timeout == 6
            captured.append(req)
            return Response()

    def opener(*handlers):
        assert handlers[0].redirect_request(None, None, 302, None, {}, "https://attacker.example") is None
        return Opener()

    monkeypatch.setattr(providers.request, "build_opener", opener)
    transport = JSONTransport()
    transport.get("guardian", "search", {"api-key": "test-only-guardian", "q": "Chelsea & Arsenal"}, {})
    parts = urlsplit(captured[0].full_url)
    assert parts.hostname == "content.guardianapis.com"
    assert parse_qs(parts.query)["q"] == ["Chelsea & Arsenal"]
    transport.get("football-data.org", "competitions/PL/standings", {}, {"X-Auth-Token": "test-only-football"})
    assert captured[1].get_header("X-auth-token") == "test-only-football"
    with pytest.raises(ProviderError):
        transport.get("attacker", "search", {}, {})


def test_singleflight_cache_ownership_and_nonblocking_executor():
    async def check():
        transport, clock = Transport(), Clock()
        transport.block = threading.Event()
        service = PlatformService(football_key="test-only-football", transport=transport, clock=clock)
        try:
            first = asyncio.create_task(service.standings())
            second = asyncio.create_task(service.standings())
            for _ in range(50):
                if transport.calls:
                    break
                await asyncio.sleep(0.002)
            # The event loop remains responsive while real network work is blocked.
            assert not first.done() and not second.done()
            assert len(transport.calls) == 1
            transport.block.set()
            one, two = await asyncio.gather(first, second)
            one["tables"].clear()
            assert two["tables"]
            assert (await service.standings())["tables"]
            assert len(transport.calls) == 1
            assert "test-only-football" not in json.dumps(two)
        finally:
            transport.block.set()
            await service.close()
    run(check())


def test_stale_fallback_retry_suppression_and_guardian_hard_retention():
    async def check():
        transport, clock = Transport(), Clock()
        service = PlatformService(guardian_key="test-only-guardian", transport=transport, clock=clock)
        try:
            initial = await service.news()
            assert initial["content_expires_at"] == clock.now + 86400
            clock.now += 601
            transport.failure = ProviderError("rate_limited", 60)
            stale = await service.news()
            assert stale["status"] == "ok" and stale["stale"]
            assert stale["provider_status"] == "rate_limited" and stale["fetched_at"] == initial["fetched_at"]
            assert len(transport.calls) == 2
            assert (await service.news())["stale"]
            assert len(transport.calls) == 2
            clock.now = initial["content_expires_at"]
            expired = await service.news()
            assert expired["articles"] == [] and expired["fetched_at"] is None
            assert expired["status"] == "rate_limited" and not service._cache
        finally:
            await service.close()
    run(check())


def test_guardian_per_second_and_daily_quota_no_retry_fanout():
    async def check():
        transport, clock = Transport(), Clock()
        service = PlatformService(guardian_key="test-only-guardian", transport=transport, clock=clock)
        try:
            assert (await service.news(query="Chelsea"))["status"] == "ok"
            assert (await service.news(query="Arsenal"))["status"] == "rate_limited"
            assert len(transport.calls) == 1
            clock.now += 2
            service._guardian_calls = 500
            assert (await service.news(query="Liverpool"))["status"] == "rate_limited"
            assert len(transport.calls) == 1
            clock.now = (int(clock.now // 86400) + 1) * 86400
            assert (await service.news(query="Liverpool"))["status"] == "ok"
            assert len(transport.calls) == 2
        finally:
            await service.close()
    run(check())


def test_full_catalog_is_exactly_eight_calls_then_cached_and_keeps_real_teams():
    async def check():
        transport = Transport()
        service = PlatformService(football_key="test-only-football", transport=transport)
        try:
            loaded = await service.catalog(load_teams=True)
            assert loaded["team_catalog_status"] == "ready" and len(loaded["teams"]) == 16
            assert len(transport.calls) == 8
            again = await service.catalog(load_teams=True)
            assert len(again["loaded_competitions"]) == 8 and len(transport.calls) == 8
            await service.standings("PL")
            assert len(transport.calls) == 8
        finally:
            await service.close()
    run(check())


@pytest.mark.parametrize("operation_spec", [("standings", "https://attacker.example"),
                                     ("news", "unknown"), ("news_query", "x" * 121),
                                     ("catalog", "bad\nquery")])
def test_invalid_public_inputs_never_call_provider(operation_spec):
    async def check():
        transport = Transport()
        service = PlatformService(football_key="test", guardian_key="test", transport=transport)
        try:
            operation, value = operation_spec
            with pytest.raises(ValueError):
                if operation == "standings":
                    await service.standings(value)
                elif operation == "news":
                    await service.news(value)
                elif operation == "news_query":
                    await service.news(query=value)
                else:
                    await service.catalog(value)
            assert transport.calls == []
        finally:
            await service.close()
    run(check())


async def http_request(port, target, *, origin="http://localhost:3030", method="GET", headers=""):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    origin_line = f"Origin: {origin}\r\n" if origin is not None else ""
    writer.write(f"{method} {target} HTTP/1.1\r\nHost: 127.0.0.1\r\n{origin_line}{headers}\r\n".encode())
    await writer.drain()
    raw = await reader.read()
    writer.close()
    await writer.wait_closed()
    head, body = raw.split(b"\r\n\r\n", 1)
    return int(head.split(b" ")[1]), head.decode(), json.loads(body) if body else None


def test_actual_local_http_routes_cors_and_caption_callback_without_network():
    async def check():
        called = []

        def captions(query):
            called.append((query, threading.current_thread().name))
            return {"status": "unavailable", "match_id": query.get("match_id"), "cues": []}

        service = PlatformService()
        server = PlatformHTTPServer(service, port=0, extra_routes={"/api/captions": captions})
        await server.start()
        try:
            status, headers, catalog = await http_request(server.port, "/api/catalog?q=EPL")
            assert status == 200 and catalog["matches"][0]["competition_code"] == "PL"
            assert "Access-Control-Allow-Origin: http://localhost:3030" in headers
            assert "Cache-Control: no-store" in headers
            status, _, table = await http_request(server.port, "/api/standings?competition=PL", origin=None)
            assert status == 200 and table["status"] == "missing_key"
            status, _, caption = await http_request(server.port, "/api/captions?match_id=cam-1")
            assert status == 200 and caption["match_id"] == "cam-1"
            assert called[0][0] == {"match_id": "cam-1"}
            assert called[0][1].startswith("platform-provider")
            status, _, _ = await http_request(server.port, "/api/news", method="OPTIONS")
            assert status == 204
        finally:
            await server.close()
        assert not server._connections and service._closed
    run(check())


@pytest.mark.parametrize("target,origin,method,headers,expected", [
    ("/api/news", "https://attacker.example", "GET", "", 403),
    ("/api/news", None, "POST", "", 405),
    ("/api/standings?competition=ZZ", None, "GET", "", 400),
    ("/api/news?q=one&q=two", None, "GET", "", 400),
    ("/api/catalog?load_teams=yes", None, "GET", "", 400),
    ("https://attacker.example/api/news", None, "GET", "", 400),
    ("/api/news", None, "GET", "Content-Length: 1\r\n", 400),
    ("/api/news", None, "GET", "Origin: http://localhost:3030\r\nOrigin: http://localhost:3000\r\n", 400),
    ("/missing", None, "GET", "", 404),
])
def test_actual_http_rejects_unsafe_invalid_or_unsupported_requests(target, origin, method, headers, expected):
    async def check():
        transport = Transport()
        server = PlatformHTTPServer(PlatformService(transport=transport), port=0)
        await server.start()
        try:
            status, _, _ = await http_request(server.port, target, origin=origin, method=method, headers=headers)
            assert status == expected and transport.calls == []
        finally:
            await server.close()
    run(check())


def test_provider_exception_secrets_are_sanitized_and_failures_negative_cached():
    async def check():
        transport = Transport()
        transport.failure = RuntimeError("https://content.guardianapis.com/search?api-key=DO-NOT-EXPOSE")
        service = PlatformService(guardian_key="DO-NOT-EXPOSE", transport=transport)
        try:
            result = await service.news()
            assert result["status"] == "unavailable" and "DO-NOT-EXPOSE" not in json.dumps(result)
            await service.news()
            assert len(transport.calls) == 1
        finally:
            await service.close()
    run(check())


def test_provider_retry_after_cannot_be_bypassed_by_changing_news_search():
    async def check():
        transport, clock = Transport(), Clock()
        transport.failure = ProviderError("rate_limited", 60)
        service = PlatformService(guardian_key="test-only-guardian", transport=transport, clock=clock)
        try:
            assert (await service.news(query="Chelsea"))["status"] == "rate_limited"
            clock.now += 2
            transport.failure = None
            assert (await service.news(query="Arsenal"))["status"] == "rate_limited"
            assert len(transport.calls) == 1
            clock.now += 60
            assert (await service.news(query="Arsenal"))["status"] == "ok"
            assert len(transport.calls) == 2
        finally:
            await service.close()
    run(check())


def test_football_quota_ten_per_rolling_minute_and_exact_boundary():
    service, clock = PlatformService(), Clock()
    service._clock = clock
    for _ in range(10):
        service._reserve("football-data.org")
    with pytest.raises(ProviderError, match="rate_limited"):
        service._reserve("football-data.org")
    clock.now += 59.99
    with pytest.raises(ProviderError):
        service._reserve("football-data.org")
    clock.now += 0.01
    service._reserve("football-data.org")
    run(service.close())


def test_guardian_content_is_deleted_when_idle_not_only_when_requested():
    async def check():
        service = PlatformService(guardian_key="test-only-guardian", transport=Transport())
        service.HARD_RETENTION_SECONDS = 0.01
        try:
            assert (await service.news())["articles"]
            assert service._cache
            await asyncio.sleep(0.03)
            assert not service._cache and not service._expiry_handles
        finally:
            await service.close()
    run(check())


def test_explicit_champions_league_groups_are_preserved_not_flattened():
    async def check():
        service = PlatformService(football_key="test-only-football", transport=Transport())
        try:
            result = await service.standings("CL")
            assert result["competition"]["code"] == "CL"
            catalog = await service.catalog()
            optional = next(item for item in catalog["competitions"] if item["code"] == "CL")
            assert optional["default"] is False
        finally:
            await service.close()
    run(check())
    payload = standing("CL")
    payload["competition"]["type"] = "LEAGUE_CUP"
    payload["standings"][0].update(stage="LEAGUE_STAGE", group="League phase")
    result = standings_payload(payload, "CL")
    assert result["tables"][0]["stage"] == "LEAGUE_STAGE" and result["tables"][0]["group"] == "League phase"


def test_concurrent_complete_catalog_requests_coalesce_all_eight_provider_calls():
    async def check():
        transport = Transport()
        service = PlatformService(football_key="test-only-football", transport=transport)
        try:
            one, two = await asyncio.gather(service.catalog(load_teams=True), service.catalog(load_teams=True))
            assert one["team_catalog_status"] == two["team_catalog_status"] == "ready"
            assert len(transport.calls) == 8
        finally:
            await service.close()
    run(check())


def test_failure_cache_is_bounded_even_for_unexpected_provider_exceptions():
    async def check():
        transport, clock = Transport(), Clock()
        transport.failure = RuntimeError("test failure")
        service = PlatformService(guardian_key="test-only-guardian", transport=transport, clock=clock)
        try:
            for index in range(70):
                await service.news(query=f"query {index}")
                clock.now += 2
            assert len(service._failures) == service.MAX_CACHE and not service._inflight
        finally:
            await service.close()
    run(check())


def test_http_close_cancels_idle_clients_and_callback_bad_json_is_safe():
    async def check():
        server = PlatformHTTPServer(PlatformService(), port=0,
                                    extra_routes={"/api/bad": lambda _: {"value": float("nan")}})
        await server.start()
        _, writer = await asyncio.open_connection("127.0.0.1", server.port)
        try:
            status, _, data = await http_request(server.port, "/api/bad")
            assert status == 502 and data == {"status": "unavailable"}
            await asyncio.wait_for(server.close(), 0.5)
            assert not server._connections and not server._writers
        finally:
            writer.close()
            await writer.wait_closed()
            await server.close()
    run(check())


@pytest.mark.parametrize("origin", ["*", "https://example.com/path", "http://user@example.com",
                                     "http://example.com?query=1", "http://example.com\r\nInjected: yes"])
def test_invalid_api_origin_configuration_rejected(origin):
    with pytest.raises(ValueError, match="invalid_api_origins"):
        PlatformHTTPServer(allowed_origins=[origin])
