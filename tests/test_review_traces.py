import json

from backend import review_traces


def write_records(path, records):
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_review_traces_reports_execution_privacy(tmp_path, monkeypatch, capsys):
    trace_path = tmp_path / "traces.jsonl"
    write_records(
        trace_path,
        [
            {
                "type": "intent",
                "traceId": "trace-1",
                "request": {"url": "https://crm.example.com/customer"},
                "response": {"intent": "trying to extract useful facts"},
                "privacy": {
                    "sensitivity": "personal",
                    "route": "cloud_redacted",
                    "redactionCount": 1,
                    "findingKinds": ["email"],
                },
            },
            {
                "type": "execution",
                "traceId": "trace-1",
                "actionId": "extract_key_facts",
                "metadata": {
                    "status": "done",
                    "privacy": {
                        "sensitivity": "secret",
                        "route": "local",
                        "redactionCount": 2,
                        "findingKinds": ["password"],
                    },
                },
            },
        ],
    )
    monkeypatch.setattr(review_traces, "TRACE_PATH", trace_path)

    review_traces.main()

    output = capsys.readouterr().out
    assert "Total intent redactions: 1" in output
    assert "Total execution redactions: 2" in output
    assert "Intent privacy sensitivity labels" in output
    assert "  personal: 1" in output
    assert "Execution privacy sensitivity labels" in output
    assert "  secret: 1" in output
    assert "Execution privacy routes" in output
    assert "  local: 1" in output
