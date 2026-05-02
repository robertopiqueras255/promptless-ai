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


def test_review_traces_prints_product_quality_report(tmp_path, monkeypatch, capsys):
    trace_path = tmp_path / "traces.jsonl"
    write_records(
        trace_path,
        [
            {
                "type": "intent",
                "traceId": "trace-pricing",
                "request": {"url": "https://example.com/pricing"},
                "response": {"intent": "trying to compare options"},
                "privacy": {"sensitivity": "public", "route": "cloud_redacted"},
            },
            {
                "type": "feedback",
                "traceId": "trace-pricing",
                "event": "shown",
                "metadata": {"actionIds": ["compare_visible_options", "extract_key_facts"]},
            },
            {"type": "feedback", "traceId": "trace-pricing", "event": "accepted", "actionId": "compare_visible_options"},
            {"type": "execution", "traceId": "trace-pricing", "actionId": "compare_visible_options", "metadata": {"status": "done"}},
            {"type": "feedback", "traceId": "trace-pricing", "event": "thumbs_up", "actionId": "compare_visible_options"},
            {
                "type": "intent",
                "traceId": "trace-home",
                "request": {"url": "https://example.com/home"},
                "response": {"intent": "trying to take the next action"},
                "privacy": {"sensitivity": "public", "route": "cloud_redacted"},
            },
            {
                "type": "feedback",
                "traceId": "trace-home",
                "event": "shown",
                "metadata": {"actionIds": ["what_should_i_do_next"]},
            },
            {"type": "feedback", "traceId": "trace-home", "event": "dismissed", "actionId": "what_should_i_do_next"},
        ],
    )
    monkeypatch.setattr(review_traces, "TRACE_PATH", trace_path)

    review_traces.main()

    output = capsys.readouterr().out
    assert "Promptless AI Quality Report" in output
    assert "Pages observed: 2" in output
    assert "Suggestions shown: 3" in output
    assert "Accepted actions: 1" in output
    assert "Dismissed: 1" in output
    assert "Executed actions: 1" in output
    assert "Prompt avoidance rate: 1/3 (33.3%)" in output
    assert "Best actions" in output
    assert "compare_visible_options: accepted 1/1 (100.0%), executed 1, thumbs +1/-0" in output
    assert "Noisy actions" in output
    assert "what_should_i_do_next: dismissed 1/1 (100.0%), accepted 0/1 (0.0%)" in output
    assert "Pages with most dismissals" in output
    assert "https://example.com/home: 1" in output
