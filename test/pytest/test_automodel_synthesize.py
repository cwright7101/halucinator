"""Tests for the offline trace synthesizer (halucinator.automodel)."""
import sqlite3

from halucinator.automodel.synthesize import synthesize_from_db, to_yaml


def _make_db(tmp_path, rows):
    db = str(tmp_path / "trace.sqlite")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE mmio_trace (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " region TEXT, seq INTEGER, pc INTEGER, addr INTEGER, size INTEGER,"
        " value INTEGER, rw TEXT)")
    conn.executemany(
        "INSERT INTO mmio_trace(region, seq, pc, addr, size, value, rw)"
        " VALUES ('r',?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


def test_classifies_status_data_and_control(tmp_path):
    rows = []
    seq = 0
    # Status register: same pc reads same addr 20x in a row (spin-wait).
    for _ in range(20):
        rows.append((seq, 0x8000, 0x40023800, 4, 0, "r")); seq += 1
    # Data-out (UART): printable byte writes, never read.
    for ch in b"Grbl 0.8c\n":
        rows.append((seq, 0x8100, 0x40004404, 1, ch, "w")); seq += 1
    # Control register: a few writes, no spin-wait.
    for v in (1, 2, 3):
        rows.append((seq, 0x8200, 0x40020000, 4, v, "w")); seq += 1

    db = _make_db(tmp_path, rows)
    models = synthesize_from_db(db)

    assert models[0x40023800].klass == "status"
    assert models[0x40023800].max_consecutive_reads >= 8
    assert models[0x40004404].klass == "data_out"
    assert models[0x40020000].klass == "control"

    y = to_yaml(models)
    assert "class: status" in y and "class: data_out" in y


def test_llm_annotation_with_mock(tmp_path):
    rows = [(0, 0x8000, 0x40000000, 4, 0, "r")]
    db = _make_db(tmp_path, rows)
    models = synthesize_from_db(db, llm_config={"provider": "mock"})
    assert models[0x40000000].llm_label == "MOCK_LLM_RESPONSE"
