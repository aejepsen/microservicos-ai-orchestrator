"""OOD guard por resíduo de subespaço (padrão AI-Orchestrator subspace_guard).

Fit: SVD do corpus in-domain centrado; k componentes cobrindo 95% da
variância. Resíduo = norma da componente ortogonal ao subespaço,
normalizada pela norma do vetor centrado (∈ [0,1]).

Calibração de threshold é SEMPRE leave-one-out (lição AIO: split 80/20
superestima). Amostras `is_clarification` são rejeitadas do fit (lição
AIO: fora de domínio por design, contaminam o subespaço).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

_VARIANCE_TARGET = 0.95
_MAX_COMPONENTS = 64
MIN_FIT_SAMPLES = 30


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


class SbertEmbedder:
    """Wrapper do SentenceTransformer; carregado no boot (lazy proibido pela spec)."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts, show_progress_bar=False), dtype=np.float64)


@dataclass(frozen=True)
class OodVerdict:
    flagged: bool
    residual: float
    threshold: float


@dataclass(frozen=True)
class FitReport:
    n_samples: int
    n_rejected_clarification: int
    threshold: float
    auc_loo: float
    corpus_hash: str


def _subspace(embeddings: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Retorna (média, componentes[k, dim]) cobrindo 95% da variância."""
    mean = embeddings.mean(axis=0)
    centered = embeddings - mean
    _, s, vt = np.linalg.svd(centered, full_matrices=False)
    var = s**2
    cum = np.cumsum(var) / var.sum()
    k = int(np.searchsorted(cum, _VARIANCE_TARGET) + 1)
    k = min(k, _MAX_COMPONENTS, len(s))
    return mean, vt[:k]


def _residual(vec: np.ndarray, mean: np.ndarray, components: np.ndarray) -> float:
    centered = vec - mean
    norm = float(np.linalg.norm(centered))
    if norm == 0.0:
        return 0.0
    proj = components.T @ (components @ centered)
    return float(np.linalg.norm(centered - proj) / norm)


def _auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """AUC por estatística de Mann-Whitney (pos = OOD, escore maior = mais OOD)."""
    combined = np.concatenate([pos, neg])
    ranks = combined.argsort().argsort().astype(np.float64) + 1.0
    r_pos = ranks[: len(pos)].sum()
    u = r_pos - len(pos) * (len(pos) + 1) / 2.0
    return float(u / (len(pos) * len(neg)))


class OodGuard:
    def __init__(self, models_dir: str) -> None:
        self._dir = Path(models_dir)
        self._mean: np.ndarray | None = None
        self._components: np.ndarray | None = None
        self._threshold: float | None = None
        self._meta: dict[str, Any] = {}
        self._load()

    @property
    def fitted(self) -> bool:
        return self._components is not None and self._threshold is not None

    @property
    def meta(self) -> dict[str, Any]:
        return dict(self._meta)

    def _load(self) -> None:
        npz_path = self._dir / "ood_subspace.npz"
        meta_path = self._dir / "ood_meta.json"
        if not (npz_path.exists() and meta_path.exists()):
            return
        data = np.load(npz_path)
        self._mean = data["mean"]
        self._components = data["components"]
        self._meta = json.loads(meta_path.read_text())
        self._threshold = float(self._meta["threshold"])

    def fit(
        self,
        in_domain: list[dict[str, object]],
        ood_calibration: list[str],
        embedder: Embedder,
    ) -> FitReport:
        rejected = sum(1 for s in in_domain if bool(s.get("is_clarification", False)))
        texts = [str(s["text"]) for s in in_domain if not bool(s.get("is_clarification", False))]
        if len(texts) < MIN_FIT_SAMPLES:
            raise ValueError(
                f"corpus insuficiente: {len(texts)} amostras validas (minimo {MIN_FIT_SAMPLES})"
            )

        emb_in = embedder.encode(texts)
        emb_ood = embedder.encode(ood_calibration)

        # LOO: resíduo de cada amostra in-domain contra subespaço fitado sem ela.
        loo_residuals = np.empty(len(texts))
        idx = np.arange(len(texts))
        for i in idx:
            mean_i, comp_i = _subspace(emb_in[idx != i])
            loo_residuals[i] = _residual(emb_in[i], mean_i, comp_i)

        # Subespaço final (corpus completo) — usado em runtime e p/ escorar o OOD calib.
        mean, components = _subspace(emb_in)
        ood_residuals = np.array([_residual(v, mean, components) for v in emb_ood])

        auc = _auc(ood_residuals, loo_residuals)
        # Threshold: ponto de Youden (max TPR - FPR) sobre LOO in vs OOD calib.
        candidates = np.unique(np.concatenate([loo_residuals, ood_residuals]))
        best_thr, best_j = 0.5, -1.0
        for thr in candidates:
            tpr = float((ood_residuals >= thr).mean())
            fpr = float((loo_residuals >= thr).mean())
            if tpr - fpr > best_j:
                best_j, best_thr = tpr - fpr, float(thr)

        corpus_hash = hashlib.sha256("\n".join(sorted(texts)).encode()).hexdigest()[:16]
        self._mean, self._components, self._threshold = mean, components, best_thr
        self._meta = {
            "n_samples": len(texts),
            "n_rejected_clarification": rejected,
            "threshold": best_thr,
            "auc_loo": auc,
            "fitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "corpus_hash": corpus_hash,
            "n_components": int(components.shape[0]),
        }

        self._dir.mkdir(parents=True, exist_ok=True)
        np.savez(self._dir / "ood_subspace.npz", mean=mean, components=components)
        (self._dir / "ood_meta.json").write_text(json.dumps(self._meta, indent=2))

        return FitReport(
            n_samples=len(texts),
            n_rejected_clarification=rejected,
            threshold=best_thr,
            auc_loo=auc,
            corpus_hash=corpus_hash,
        )

    def check(self, text: str, embedder: Embedder) -> OodVerdict:
        if not self.fitted:
            raise RuntimeError("OOD guard sem artefato fitado")
        assert self._mean is not None
        assert self._components is not None and self._threshold is not None
        vec = embedder.encode([text])[0]
        residual = _residual(vec, self._mean, self._components)
        return OodVerdict(
            flagged=residual >= self._threshold,
            residual=round(residual, 4),
            threshold=self._threshold,
        )
