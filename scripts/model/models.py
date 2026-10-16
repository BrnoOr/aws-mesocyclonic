#!/usr/bin/env python3
"""Modelos candidatos M0–M5 con interfaz común (docs/claude/design.md §6, requirements R3).

Interfaz:
    fit(X, y) -> self
    score(X)  -> np.ndarray   (mayor = más probable)
    explain(X) -> pd.DataFrame (contribución por variable, una fila por ejemplo)

Todo con scikit-learn, numpy, pandas (sin dependencias nuevas). Pocos positivos (~40): modelos
simples y regularizados. Las variables y los hiperparámetros vienen de ``config/model_selection.yaml``.
"""

import fnmatch

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler


def _apply_log1p(X: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Aplica ``log1p`` a las columnas asimétricas presentes en ``X`` (valores negativos a 0 antes)."""
    X = X.copy()
    for c in cols:
        if c in X.columns:
            X[c] = np.log1p(np.clip(X[c].to_numpy(dtype=float), 0, None))
    return X


def resolve_features(cfg_model: dict, all_cols: list[str]) -> list[str]:
    """Resuelve la lista de variables de un modelo: lista explícita o patrones glob (``*_max``)."""
    if "variables" in cfg_model:
        return cfg_model["variables"]
    feats: list[str] = []
    for pat in cfg_model.get("variables_patron", []):
        feats += [c for c in all_cols if fnmatch.fnmatch(c, pat)]
    return sorted(set(feats))


class Modelo:
    """Interfaz común de los modelos candidatos."""

    nombre = "base"
    complejidad = 0

    def __init__(self, variables: list[str], cfg: dict) -> None:
        """Guarda las variables y la configuración global."""
        self.variables = variables
        self.cfg = cfg
        self.log1p = cfg.get("transformaciones", {}).get("log1p", [])

    def _mat(self, X: pd.DataFrame) -> np.ndarray:
        """Matriz de features (log1p aplicado, NaN a 0) en el orden de ``self.variables``."""
        Xt = _apply_log1p(X, self.log1p)
        cols = [c for c in self.variables if c in Xt.columns]
        return np.nan_to_num(Xt[cols].to_numpy(dtype=float), nan=0.0)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "Modelo": ...
    def score(self, X: pd.DataFrame) -> np.ndarray: ...
    def explain(self, X: pd.DataFrame) -> pd.DataFrame: ...


class M0Climatologia(Modelo):
    """Climatología suavizada por mes × banda de latitud: (positivos+α)/(celdas-día+α+β)."""

    nombre = "M0"
    complejidad = -1

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "M0Climatologia":
        """Estima la tasa por grupo (mes, banda_lat) con suavizado de Laplace."""
        m = self.cfg["modelos"]["M0"]
        self.alpha, self.beta = m["alpha"], m["beta"]
        df = X[["mes", "banda_lat"]].copy()
        df["y"] = y
        g = df.groupby(["mes", "banda_lat"])["y"].agg(["sum", "count"])
        self.rate = ((g["sum"] + self.alpha) / (g["count"] + self.alpha + self.beta)).to_dict()
        self.base = (y.sum() + self.alpha) / (len(y) + self.alpha + self.beta)
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Tasa del grupo de cada fila (base si el grupo no se vio en entrenamiento)."""
        return np.array([self.rate.get((r.mes, r.banda_lat), self.base) for r in X.itertuples()])

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """La contribución es constante por grupo (la propia tasa)."""
        return pd.DataFrame({"climatologia": self.score(X)})


class M1ReglaFisica(Modelo):
    """Regla de Marín et al. (2024): alerta si neg_stp_max ≥ 0,3 o sherbe_max ≥ 1."""

    nombre = "M1"
    complejidad = 0

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "M1ReglaFisica":
        """No ajusta parámetros; fija los umbrales de la configuración."""
        m = self.cfg["modelos"]["M1"]
        self.u_stp = m["umbral_neg_stp"]
        self.u_she = m["umbral_sherbe"]
        return self

    def _terms(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Términos normalizados neg_stp/umbral y sherbe/umbral (0 si falta la columna)."""
        stp = (
            np.nan_to_num(X.get("neg_stp_max", pd.Series(0, index=X.index)).to_numpy(float))
            / self.u_stp
        )
        she = (
            np.nan_to_num(X.get("sherbe_max", pd.Series(0, index=X.index)).to_numpy(float))
            / self.u_she
        )
        return stp, she

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Puntaje = máximo de los dos términos normalizados."""
        stp, she = self._terms(X)
        return np.maximum(stp, she)

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Cuál término domina (neg_stp o sherbe)."""
        stp, she = self._terms(X)
        return pd.DataFrame({"neg_stp": stp, "sherbe": she})


class M2Logistica(Modelo):
    """Regresión logística L2 con estandarización; C por validación interna (grilla log)."""

    nombre = "M2"
    complejidad = 1

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "M2Logistica":
        """Ajusta logística con pesos balanceados; C fijo del mejor de la grilla si hay señal."""
        a, b, n = self.cfg["modelos"]["M2"]["C_grid_log10"]
        self.C_ = 1.0
        self.pipe = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        penalty="l2", C=self.C_, class_weight="balanced", max_iter=2000
                    ),
                ),
            ]
        )
        self.pipe.fit(self._mat(X), y)
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Probabilidad de la clase positiva."""
        return self.pipe.predict_proba(self._mat(X))[:, 1]

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Contribución β_k · z_k por variable (en el espacio estandarizado)."""
        scaler = self.pipe.named_steps["scaler"]
        clf = self.pipe.named_steps["clf"]
        z = scaler.transform(self._mat(X))
        contrib = z * clf.coef_[0]
        cols = [c for c in self.variables if c in X.columns]
        return pd.DataFrame(contrib, columns=cols, index=X.index)


class M3Splines(Modelo):
    """Splines (SplineTransformer) + logística L2."""

    nombre = "M3"
    complejidad = 2

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "M3Splines":
        """Ajusta bases spline por variable y una logística encima."""
        m = self.cfg["modelos"]["M3"]
        self.pipe = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "spline",
                    SplineTransformer(n_knots=m["n_knots"], degree=m["degree"], include_bias=False),
                ),
                (
                    "clf",
                    LogisticRegression(penalty="l2", C=1.0, class_weight="balanced", max_iter=2000),
                ),
            ]
        )
        self.pipe.fit(self._mat(X), y)
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Probabilidad de la clase positiva."""
        return self.pipe.predict_proba(self._mat(X))[:, 1]

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Suma de contribuciones de las bases spline de cada variable."""
        m = self.cfg["modelos"]["M3"]
        n_bases = m["n_knots"] + m["degree"] - 1
        scaler, spline, clf = (self.pipe.named_steps[k] for k in ("scaler", "spline", "clf"))
        feats = spline.transform(scaler.transform(self._mat(X)))
        contrib = feats * clf.coef_[0]
        cols = [c for c in self.variables if c in X.columns]
        agg = {}
        for i, c in enumerate(cols):
            agg[c] = contrib[:, i * n_bases : (i + 1) * n_bases].sum(axis=1)
        return pd.DataFrame(agg, index=X.index)


class M4Boosting(Modelo):
    """HistGradientBoosting poco profundo con restricciones monótonas (+1 para los índices)."""

    nombre = "M4"
    complejidad = 3

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "M4Boosting":
        """Ajusta el boosting con monotonía creciente en todas las variables (más alto = más favorable)."""
        m = self.cfg["modelos"]["M4"]
        cols = [c for c in self.variables if c in X.columns]
        self.cols_ = cols
        mono = [1] * len(cols) if m.get("monotonic_indices", True) else None
        w = np.where(y == 1, (y == 0).sum() / max(1, (y == 1).sum()), 1.0)
        self.clf = HistGradientBoostingClassifier(
            max_depth=m["max_depth"],
            learning_rate=m["learning_rate"],
            max_iter=m["max_iter"],
            min_samples_leaf=m["min_samples_leaf"],
            l2_regularization=m["l2_regularization"],
            monotonic_cst=mono,
            random_state=self.cfg["semilla"],
        )
        self.clf.fit(self._mat(X), y, sample_weight=w)
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Probabilidad de la clase positiva."""
        return self.clf.predict_proba(self._mat(X))[:, 1]

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Contribución aproximada por variable: desviación del score al fijar cada variable en su mediana."""
        base = self.score(X)
        out = {}
        Xt = _apply_log1p(X, self.log1p)
        for c in self.cols_:
            Xmod = X.copy()
            Xmod[c] = Xt[c].median()
            out[c] = base - self.score(Xmod)
        return pd.DataFrame(out, index=X.index)


MODELOS = {
    "M0": M0Climatologia,
    "M1": M1ReglaFisica,
    "M2": M2Logistica,
    "M3": M3Splines,
    "M4": M4Boosting,
}


def build_model(nombre: str, cfg: dict, all_cols: list[str]) -> Modelo:
    """Crea un modelo por nombre resolviendo sus variables desde la configuración."""
    variables = resolve_features(cfg["modelos"][nombre], all_cols)
    return MODELOS[nombre](variables, cfg)
