
from app.ingestion import file_already_ingested, make_batch_id


def test_batch_id_is_deterministic():
    first = make_batch_id(
        "drop_1", "data/drop_1/example.csv", "abc123"
    )
    second = make_batch_id(
        "drop_1", "data/drop_1/example.csv", "abc123"
    )

    assert first == second


def test_different_file_hash_creates_different_batch_id():
    first = make_batch_id("drop_1", "example.csv", "hash1")
    second = make_batch_id("drop_1", "example.csv", "hash2")

    assert first != second
