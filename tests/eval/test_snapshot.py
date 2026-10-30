"""Regression tests for pinning the snapshot to a baseline model."""

from app.eval import snapshot


def _capture(monkeypatch):
    calls: dict[str, dict] = {}

    def fake_latest_raw(system, model=None, output_dir=None):
        calls[system] = {"model": model, "output_dir": output_dir}
        return None

    monkeypatch.setattr(snapshot, "latest_raw", fake_latest_raw)
    return calls


def test_load_all_pins_baseline_model(monkeypatch, tmp_path):
    calls = _capture(monkeypatch)

    data = snapshot.load_all(
        behaviors={}, output_dir=tmp_path, model=snapshot.BASELINE_MODEL
    )

    assert data == {}
    for system in ("direct", "direct+rag", "harness"):
        assert calls[system] == {
            "model": snapshot.BASELINE_MODEL,
            "output_dir": tmp_path,
        }
    # oracle issues no model call, so its dumps stay under raw/no-model/.
    assert calls["oracle"] == {
        "model": snapshot.NO_MODEL_SLUG,
        "output_dir": tmp_path,
    }


def test_load_all_defaults_to_newest_across_models(monkeypatch, tmp_path):
    calls = _capture(monkeypatch)

    snapshot.load_all(behaviors={}, output_dir=tmp_path)

    assert all(call["model"] is None for call in calls.values())
    # The output directory must never be passed positionally as ``model``.
    assert all(call["output_dir"] == tmp_path for call in calls.values())
