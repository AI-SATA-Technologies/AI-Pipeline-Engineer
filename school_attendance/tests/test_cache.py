import numpy as np

from database import DedupIndex, EmbeddingCache


def _unit(*head) -> np.ndarray:
    v = np.zeros(512, dtype=np.float32)
    v[: len(head)] = head
    return v / np.linalg.norm(v)


def test_cache_add_len_claim_evicts():
    cache = EmbeddingCache()
    a, b = _unit(1.0), _unit(0.0, 1.0)
    cache.add('A', a)
    cache.add('B', b)
    assert len(cache) == 2

    assert cache.claim(a) == 'A'      # match -> claimed
    assert len(cache) == 1            # and evicted
    assert cache.claim(a) is None     # A gone, B is orthogonal -> no match
    assert cache.claim(b) == 'B'
    assert len(cache) == 0


def test_cache_claim_below_threshold_keeps_entry():
    cache = EmbeddingCache()
    cache.add('A', _unit(1.0))
    assert cache.claim(_unit(0.0, 1.0)) is None  # cosine 0 < SIMILARITY_THRESHOLD
    assert len(cache) == 1                        # not evicted


def test_dedup_find_match():
    idx = DedupIndex()
    idx.add('A', _unit(1.0))
    reg, score = idx.find_match(_unit(1.0))
    assert reg == 'A'
    assert score > 0.99

    reg2, _ = idx.find_match(_unit(0.0, 1.0))
    assert reg2 is None
