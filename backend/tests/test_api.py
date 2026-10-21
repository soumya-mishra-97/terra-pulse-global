def test_health_reports_demo_mode_without_leaking_config(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["dataset_loaded"] and body["llm_mode"] == "demo"
    assert "key" not in r.text.lower()


def test_correlation_id_is_echoed_or_generated(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "req-12345678"})
    assert r.headers["X-Request-ID"] == "req-12345678"
    r2 = client.get("/api/v1/health", headers={"X-Request-ID": "bad id with spaces"})
    assert r2.headers["X-Request-ID"] != "bad id with spaces" and len(r2.headers["X-Request-ID"]) == 32


def test_summary_has_provenance_and_labels_synthetic_data(client):
    body = client.get("/api/v1/population/summary").json()
    prov = body["provenance"]
    for key in ("dataset_name", "publisher", "release_version", "reference_date", "license", "imported_at",
                "uncertainty_note", "freshness", "snapshot_id"):
        assert prov[key] not in (None, "")
    assert prov["is_synthetic"] is True and prov["data_label"].startswith("DEMO DATA")
    assert body["estimate"]["reference_date"] == "2025-07-01"
    assert body["estimate"]["value_kind"] == "estimate"
    counter = body["illustrative_counter"]
    assert counter["value_kind"] == "illustrative_projection"
    assert "not an official" in counter["label"].lower()
    assert body["history"][0]["year"] == 2015


def test_countries_sort_filter_and_paginate(client):
    body = client.get("/api/v1/population/countries", params={"sort": "population", "limit": 2}).json()
    assert [i["iso3"] for i in body["items"]] == ["IND", "PAK"] and body["total"] == 4
    body = client.get("/api/v1/population/countries", params={"q": "lanka"}).json()
    assert [i["iso3"] for i in body["items"]] == ["LKA"]
    body = client.get("/api/v1/population/countries", params={"sort": "name", "order": "asc", "offset": 3}).json()
    assert [i["name"] for i in body["items"]] == ["Sri Lanka"]


def test_countries_rejects_invalid_params(client):
    r = client.get("/api/v1/population/countries", params={"limit": 0})
    assert r.status_code == 422 and r.json()["error"]["title"] == "Invalid request"
    assert client.get("/api/v1/population/countries", params={"sort": "drop table"}).status_code == 422


def test_history_returns_change_and_reference_dates(client):
    body = client.get("/api/v1/population/countries/ind/history", params={"start": 2020}).json()
    assert body["iso3"] == "IND" and body["points"][0]["year"] == 2020
    assert body["points"][0]["reference_date"] == "2020-07-01"
    assert body["change"]["start_year"] == 2020 and body["change"]["end_year"] == 2025


def test_history_rejects_non_iso3_instead_of_truncating(client):
    # "INDONESIA" must not be truncated to "IND" (India).
    assert client.get("/api/v1/population/countries/INDONESIA/history").status_code == 422
    assert client.get("/api/v1/population/countries/IN/history").status_code == 422


def test_history_unknown_country_and_metric(client):
    assert client.get("/api/v1/population/countries/XXX/history").status_code == 404
    assert client.get("/api/v1/population/countries/IND/history", params={"metric": "secret_metric"}).status_code == 404


def test_regions_and_sources(client):
    body = client.get("/api/v1/population/regions").json()
    assert body["world"]["code"] == "WLD" and [r["code"] for r in body["regions"]] == ["SAS"]
    sources = client.get("/api/v1/population/sources").json()
    assert sources[0]["is_active"] and sources[0]["is_synthetic"]


def test_empty_database_returns_503_not_500(empty_client):
    r = empty_client.get("/api/v1/population/summary")
    assert r.status_code == 503 and "import" in r.json()["error"]["detail"].lower()
    assert empty_client.get("/api/v1/health").json()["status"] == "degraded"


def test_docs_are_whitelisted(client):
    assert client.get("/api/v1/docs/readme").status_code in (200, 404)
    assert client.get("/api/v1/docs/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/v1/docs/unknown").status_code == 404


def test_metrics_endpoint_counts_requests(client):
    client.get("/api/v1/health")
    snap = client.get("/api/v1/metrics").json()
    assert snap["counters"].get("http.2xx", 0) >= 1


def test_copilot_chat_validation(client):
    assert client.post("/api/v1/copilot/chat", json={"question": "x"}).status_code == 422
    assert client.post("/api/v1/copilot/chat", json={"question": "a" * 1001}).status_code == 422
    assert client.post("/api/v1/copilot/chat", json={}).status_code == 422


def test_copilot_chat_demo_mode_end_to_end(client):
    r = client.post("/api/v1/copilot/chat", json={"question": "Compare India and Pakistan population growth since 2015"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "demo" and not body["refused"]
    assert body["plan"]["intent"] == "compare" and body["plan"]["countries"] == ["IND", "PAK"]
    assert body["validation"]["output"]["passed"]
    assert body["citations"][0]["label"] == "S1"
    assert any("DEMO DATA" in x for x in body["limitations"])
    assert [t["node"] for t in body["trace"]][0] == "supervisor"


def test_copilot_rate_limited(client):
    client.app.state.container.settings.copilot_requests_per_minute = 2
    for _ in range(2):
        assert client.post("/api/v1/copilot/chat", json={"question": "What is the world population?"}).status_code == 200
    r = client.post("/api/v1/copilot/chat", json={"question": "What is the world population?"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_invalid_user_header_rejected(client):
    r = client.post("/api/v1/copilot/chat", json={"question": "world population?"}, headers={"X-User-Id": "a b;c"})
    assert r.status_code == 400
