import io
import time

import pytest
from pypdf import PdfReader

from app.integrations.storage import LocalFileStorage, StorageError
from app.reports.builder import SectionBuilder
from app.reports.catalog import SECTION_ORDER
from app.reports.markdown import esc, render_markdown
from tests.conftest import FakeLLM

ALL = list(SECTION_ORDER)


def gen(client, country="IND", period="10y", sections=ALL, user="alice", key=None):
    headers = {"X-User-Id": user}
    if key:
        headers["Idempotency-Key"] = key
    return client.post("/api/v1/reports/generate", json={"country_code": country, "period": period,
                                                         "sections": sections}, headers=headers)


def test_supported_countries_and_options(client):
    countries = client.get("/api/v1/reports/countries").json()
    assert {c["iso3"] for c in countries} == {"IND", "PAK", "LKA", "BTN"}  # aggregates excluded
    assert next(c for c in countries if c["iso3"] == "IND")["flag"] == "🇮🇳"
    opts = client.get("/api/v1/reports/options").json()
    assert len(opts["sections"]) == 16 and "executive_summary" in opts["required"]


def test_generate_preview_and_history(client):
    r = gen(client)
    assert r.status_code == 202
    rep = r.json()
    assert rep["status"] == "completed" and rep["progress"] == 100
    detail = client.get(f"/api/v1/reports/{rep['id']}", headers={"X-User-Id": "alice"}).json()
    content = detail["content"]
    assert [s["id"] for s in content["sections"]] == ALL
    assert content["country"]["name"] == "India" and content["data_reference_date"] == "2025-07-01"
    assert content["provenance"]["is_synthetic"] and "not real-time" in content["disclaimer"]
    assert detail["sources"][0]["label"] == "S1" and len(detail["sources"]) > 1
    assert detail["runs"][0]["status"] == "completed" and detail["runs"][0]["trace"]
    proj = next(s for s in content["sections"] if s["id"] == "projections")
    assert proj["status"] == "unavailable" and "Official population projections" in proj["unavailable"]
    hist = client.get("/api/v1/reports", params={"limit": 1}, headers={"X-User-Id": "alice"}).json()
    assert hist["total"] == 1 and hist["items"][0]["id"] == rep["id"]


def test_required_sections_always_included(client):
    rep = gen(client, sections=["historical_trends"]).json()
    detail = client.get(f"/api/v1/reports/{rep['id']}", headers={"X-User-Id": "alice"}).json()
    assert [s["id"] for s in detail["content"]["sections"]] == [
        "executive_summary", "country_overview", "historical_trends", "key_findings", "sources_methodology"]


def test_pdf_download_is_real_pdf_with_expected_content(client):
    rep = gen(client).json()
    r = client.get(f"/api/v1/reports/{rep['id']}/download", params={"format": "pdf"}, headers={"X-User-Id": "alice"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith('attachment; filename="terrapulse-india-10y-')
    assert r.content[:5] == b"%PDF-"
    reader = PdfReader(io.BytesIO(r.content))
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert len(reader.pages) >= 4
    assert "India" in text and "Contents" in text and "Data unavailable" in text
    assert "Page 2" in text and "[S1]" in text
    assert reader.outline  # bookmarks for the clickable table of contents


def test_markdown_download(client):
    rep = gen(client).json()
    r = client.get(f"/api/v1/reports/{rep['id']}/download", params={"format": "md"}, headers={"X-User-Id": "alice"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert r.text.startswith("# Country Intelligence Report: India") and "## References" in r.text


def test_invalid_inputs_rejected(client):
    assert gen(client, country="IN").status_code == 422
    assert gen(client, country="XXX").status_code == 404
    assert gen(client, country="SAS").status_code == 404  # aggregates are not reportable countries
    assert gen(client, period="20y").status_code == 422
    assert gen(client, sections=["executive_summary", "horoscope"]).status_code == 422
    rid = gen(client).json()["id"]
    bad_fmt = client.get(f"/api/v1/reports/{rid}/download", params={"format": "exe"}, headers={"X-User-Id": "alice"})
    assert bad_fmt.status_code == 422


@pytest.mark.parametrize("rid", ["../../etc/passwd", "..%2F..%2Fsecret", "abc", "A" * 32])
def test_report_id_path_traversal_blocked(client, rid):
    r = client.get(f"/api/v1/reports/{rid}/download", headers={"X-User-Id": "alice"})
    assert r.status_code in (404, 422)


def test_storage_rejects_traversal_keys(tmp_path):
    st = LocalFileStorage(tmp_path)
    for key in ("../x.pdf", "reports/../../x.pdf", "/etc/passwd", "reports/abc.pdf"):
        with pytest.raises(StorageError):
            st.put(key, b"x", "application/pdf")


def test_authorization_other_users_cannot_access_or_delete(client):
    rid = gen(client, user="alice").json()["id"]
    for method, url in (("get", f"/api/v1/reports/{rid}"), ("get", f"/api/v1/reports/{rid}/download"),
                        ("delete", f"/api/v1/reports/{rid}")):
        assert getattr(client, method)(url, headers={"X-User-Id": "mallory"}).status_code == 404
    assert client.get("/api/v1/reports", headers={"X-User-Id": "mallory"}).json()["total"] == 0


def test_delete_removes_report_and_files(client, settings):
    rid = gen(client).json()["id"]
    assert (settings.storage_dir / "reports" / f"{rid}.pdf").is_file()
    assert client.delete(f"/api/v1/reports/{rid}", headers={"X-User-Id": "alice"}).status_code == 204
    assert client.get(f"/api/v1/reports/{rid}", headers={"X-User-Id": "alice"}).status_code == 404
    assert not (settings.storage_dir / "reports" / f"{rid}.pdf").exists()


def test_idempotency_key_and_duplicate_request_reuse_report(client):
    a = gen(client, key="key-123456")
    b = gen(client, key="key-123456")
    assert a.json()["id"] == b.json()["id"] and b.status_code == 200 and b.headers["X-Idempotent-Replay"] == "true"
    c = gen(client)  # same parameters without a key within the window -> existing report
    assert c.json()["id"] == a.json()["id"]
    assert gen(client, key="bad key!").status_code == 400


def test_regenerate_creates_new_report(client):
    rid = gen(client).json()["id"]
    r = client.post(f"/api/v1/reports/{rid}/regenerate", headers={"X-User-Id": "alice"})
    assert r.status_code == 202 and r.json()["id"] != rid and r.json()["status"] == "completed"


def test_missing_indicator_marked_unavailable_not_fabricated(client):
    rep = gen(client, country="BTN").json()  # synthetic Bhutan has no migration data
    content = client.get(f"/api/v1/reports/{rep['id']}", headers={"X-User-Id": "alice"}).json()["content"]
    mig = next(s for s in content["sections"] if s["id"] == "migration")
    assert mig["status"] == "unavailable" and mig["metrics"] == [] and "Net migration" in mig["unavailable"]
    assert rep["status"] == "completed"


def test_failed_section_node_produces_partial_report(client, monkeypatch):
    def boom(self):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(SectionBuilder, "urban_rural", boom)
    rep = gen(client, country="PAK").json()
    assert rep["status"] == "completed"
    content = client.get(f"/api/v1/reports/{rep['id']}", headers={"X-User-Id": "alice"}).json()["content"]
    ur = next(s for s in content["sections"] if s["id"] == "urban_rural")
    assert ur["status"] == "unavailable" and "RuntimeError" in ur["notes"][0]


def test_essential_validation_failure_blocks_publication(client, factory):
    from app.repositories.orm import CountryBaselineRow

    with factory.begin() as s:
        s.query(CountryBaselineRow).filter(CountryBaselineRow.country_iso3 == "LKA",
                                           CountryBaselineRow.metric == "population_total").delete()
    rep = gen(client, country="LKA").json()
    assert rep["status"] == "blocked" and "not published" in rep["error"]
    r = client.get(f"/api/v1/reports/{rep['id']}/download", headers={"X-User-Id": "alice"})
    assert r.status_code == 409


def test_llm_narrative_with_unsupported_numbers_is_removed(client_factory):
    narrative = '{"executive_summary": "India will have 2 billion people by 2050.", ' \
                '"country_overview": "India is in South Asia [S1]."}'
    with client_factory(FakeLLM([narrative])) as c:
        rep = gen(c).json()
        content = c.get(f"/api/v1/reports/{rep['id']}", headers={"X-User-Id": "alice"}).json()["content"]
    secs = {s["id"]: s for s in content["sections"]}
    assert secs["executive_summary"]["narrative"] is None
    assert any("failed numeric" in n for n in secs["executive_summary"]["notes"])
    assert secs["country_overview"]["narrative"] == "India is in South Asia [S1]."
    assert content["mode"] == "claude"


def test_background_thread_execution_and_polling(client):
    client.app.state.container.reports.settings.report_execution = "thread"
    rep = gen(client, country="PAK").json()
    assert rep["status"] in ("queued", "running", "completed")
    for _ in range(100):
        status = client.get(f"/api/v1/reports/{rep['id']}", headers={"X-User-Id": "alice"}).json()["status"]
        if status == "completed":
            break
        time.sleep(0.05)
    assert status == "completed"


def test_interrupted_jobs_marked_failed_on_startup(client, factory):
    from app.repositories.orm import CountryReportRow

    rid = gen(client).json()["id"]
    with factory.begin() as s:
        s.get(CountryReportRow, rid).status = "running"
    assert client.app.state.container.reports.recover_interrupted() == 1
    assert client.get(f"/api/v1/reports/{rid}", headers={"X-User-Id": "alice"}).json()["status"] == "failed"


def test_active_report_limit(client, factory):
    from app.repositories.orm import CountryReportRow

    client.app.state.container.reports.settings.max_active_reports_per_user = 1
    rid = gen(client, country="PAK").json()["id"]
    with factory.begin() as s:
        s.get(CountryReportRow, rid).status = "running"
    assert gen(client, country="IND").status_code == 409


def test_markdown_escapes_untrusted_text():
    assert esc("<script>alert(1)</script>") == "&lt;script&gt;alert\\(1\\)&lt;/script&gt;"
    out = esc("[click](javascript:alert(1)) <img src=x>")
    assert "](" not in out and "<img" not in out and "\\[click\\]" in out


def test_markdown_render_handles_unicode_and_missing_values():
    content = {"title": "Country Intelligence Report: Côte d’Ivoire", "country": {"name": "Côte d’Ivoire", "iso3": "CIV"},
               "period": {"label": "Last 5 years", "start_year": 2020, "end_year": 2025}, "generated_at": "2026-01-01",
               "data_reference_date": None, "provenance": {}, "mode": "demo", "model": None, "disclaimer": "d",
               "sections": [{"id": "migration", "number": 1, "title": "Migration Trends", "status": "unavailable",
                             "summary_points": [], "metrics": [], "table": None, "unavailable": ["Net migration"],
                             "notes": [], "citations": []}], "sources": [], "limitations": [], "validation": {}}
    md = render_markdown(content)
    assert "Côte d’Ivoire" in md and "Data unavailable" in md
