from __future__ import annotations

from router_svc.bm25 import BM25, ranks_from_scores, rrf_fuse, tokenize


def test_tokenize() -> None:
    assert tokenize("Olá, Mundo 123!") == ["olá", "mundo", "123"]


def test_bm25_ranks_relevant_first() -> None:
    corpus = ["gato preto no telhado", "cachorro no quintal", "gato branco dorme"]
    scores = BM25(corpus).scores("gato")
    assert scores[0] > 0 and scores[2] > 0
    assert scores[1] == 0.0  # sem 'gato'


def test_ranks_base1() -> None:
    assert ranks_from_scores([0.1, 0.9, 0.5]) == [3, 1, 2]


def test_ranks_stable_on_ties() -> None:
    # empate: ordem estável (índice menor primeiro)
    assert ranks_from_scores([0.5, 0.5]) == [1, 2]


def test_rrf_hand_calc() -> None:
    fused = rrf_fuse([1, 2, 3], [3, 1, 2], 60)
    assert abs(fused[0] - (1/61 + 1/63)) < 1e-12
    assert abs(fused[1] - (1/62 + 1/61)) < 1e-12


def test_rrf_winner() -> None:
    fused = rrf_fuse([1, 2, 3], [3, 1, 2], 60)
    assert max(range(3), key=lambda i: fused[i]) == 1
