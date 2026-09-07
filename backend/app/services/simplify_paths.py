"""Schritt 5: Vereinfachung der Tiefenprofile fuer CATIA.

Rasterbilder erzeugen pro Millimeter mehrere Tiefenaenderungen. Ein direkter
Export erzeugt zehntausende Stuetzpunkte, an denen aeltere CATIA-STEP-
Uebersetzer sehr langsam werden oder scheitern.

Die Kette lautet daher:

1. Tonwertprofil entlang der Linie glaetten.
2. Nur ungefaehr alle ``sample_distance_mm`` abtasten.
3. Zustandswechsel Sicherheitshoehe <-> Frästiefe exakt erhalten.
4. Tiefsten Punkt je Schnittabschnitt erhalten.
5. Das Restprofil mit Ramer-Douglas-Peucker vereinfachen.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d

from app.utils.geometry import dedupe_consecutive, rdp_mask

FWHM_TO_SIGMA = 1.0 / 2.3548200450309493
"""Die Glaettungsdistanz ist als Halbwertsbreite gemeint, nicht als Sigma."""


def smooth_profile(values: np.ndarray, smoothing_px: float) -> np.ndarray:
    """Glaettet ein Tonwertprofil entlang der Linie.

    Die Glaettung wirkt auf die *Tonwerte*, nicht auf die fertigen Z-Werte.
    Dadurch bleiben die Schwellenuebergaenge hart, waehrend das Rauschen des
    Rasters verschwindet.
    """
    values = np.asarray(values, dtype=np.float32)
    if smoothing_px <= 0.5 or values.size < 3:
        return values
    sigma = max(0.4, smoothing_px * FWHM_TO_SIGMA)
    return gaussian_filter1d(values, sigma=sigma, mode="nearest")


def _true_runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """Zusammenhaengende True-Abschnitte als (start, ende_exklusiv)."""
    if flags.size == 0 or not flags.any():
        return []
    padded = np.concatenate(([False], flags, [False]))
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    return [(int(a), int(b)) for a, b in zip(edges[0::2], edges[1::2], strict=True)]


def profile_keypoints(z_values: np.ndarray, cut_flags: np.ndarray, step: int) -> np.ndarray:
    """Boolean-Maske der Punkte, die die Abtastung auf jeden Fall behaelt."""
    n = len(z_values)
    keep = np.zeros(n, dtype=bool)
    keep[:: max(1, step)] = True
    keep[0] = True
    keep[-1] = True

    # Jeder Wechsel zwischen Sicherheitshoehe und Frästiefe bleibt exakt.
    changes = np.flatnonzero(np.diff(cut_flags.astype(np.int8)) != 0)
    if changes.size:
        keep[changes] = True
        keep[changes + 1] = True

    # Der tiefste Punkt jedes Schnittabschnitts bleibt erhalten.
    for start, end in _true_runs(cut_flags):
        keep[start + int(np.argmin(z_values[start:end]))] = True
    return keep


def _preserve_deepest(points: np.ndarray, deepest: np.ndarray, tolerance: float) -> np.ndarray:
    """Stellt sicher, dass die maximale Frästiefe im Ergebnis vorkommt.

    RDP entfernt den global tiefsten Punkt, wenn er nahe genug an der
    Verbindungsgeraden liegt. Weicht das Ergebnis dadurch um mehr als die
    Toleranz von der echten Tiefe ab, wird der Punkt an seiner
    Wegposition wieder eingefuegt.
    """
    if len(points) < 2:
        return points
    if float(points[:, 1].min()) <= float(deepest[1]) + tolerance:
        return points

    t_values = points[:, 0]
    ascending = t_values[-1] >= t_values[0]
    keys = t_values if ascending else -t_values
    insert_at = int(np.searchsorted(keys, deepest[0] if ascending else -deepest[0]))
    insert_at = int(np.clip(insert_at, 1, len(points) - 1))
    return np.insert(points, insert_at, deepest, axis=0)


def simplify_profile(
    t_mm: np.ndarray,
    z_mm: np.ndarray,
    cut_flags: np.ndarray,
    sample_step_px: int,
    rdp_tolerance_mm: float,
) -> np.ndarray:
    """Vereinfacht ein (Weg, Tiefe)-Profil auf wenige Stuetzpunkte.

    Rueckgabe ist ein Nx2 Array in der Reihenfolge der Eingabe.
    """
    t_mm = np.asarray(t_mm, dtype=float)
    z_mm = np.asarray(z_mm, dtype=float)
    if len(t_mm) != len(z_mm):
        raise ValueError("t_mm und z_mm muessen gleich lang sein.")
    if len(t_mm) < 2:
        return np.column_stack([t_mm, z_mm])

    deepest_index = int(np.argmin(z_mm))
    deepest = np.array([t_mm[deepest_index], z_mm[deepest_index]], dtype=float)

    keep = profile_keypoints(z_mm, cut_flags, sample_step_px)
    sampled = np.column_stack([t_mm[keep], z_mm[keep]])
    sampled = dedupe_consecutive(sampled, tol=1e-9)
    if len(sampled) < 2:
        return np.column_stack([t_mm[[0, -1]], z_mm[[0, -1]]])

    simplified = sampled[rdp_mask(sampled, rdp_tolerance_mm)]
    return _preserve_deepest(simplified, deepest, rdp_tolerance_mm)


def reduction_percent(raw_count: int, simplified_count: int) -> float:
    """Punktreduktion in Prozent."""
    if raw_count <= 0:
        return 0.0
    return max(0.0, (1.0 - simplified_count / raw_count) * 100.0)
