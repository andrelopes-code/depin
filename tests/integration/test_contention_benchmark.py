from pathlib import Path

from benchmarks.experiments import contention


def test_contention_collection_covers_first_use_cache_and_scopes() -> None:
    result = contention.collect(samples=5, workers=4)

    assert result['samples'] == 5
    assert result['workers'] == 4
    assert set(result['profiles']) == {
        'cached_singleton',
        'request_scopes',
        'singleton_first_use',
    }
    for profile in result['profiles'].values():
        assert profile['depin']['p50_seconds'] > 0
        assert profile['depin']['p95_seconds'] >= profile['depin']['p50_seconds']
        assert profile['depin']['p99_seconds'] >= profile['depin']['p95_seconds']
        assert profile['direct']['p50_seconds'] > 0


def test_contention_cli_writes_reproducible_evidence(tmp_path: Path) -> None:
    output = tmp_path / 'contention.json'

    assert contention.main(('--samples', '5', '--workers', '4', '--out', str(output))) == 0
    assert output.is_file()
