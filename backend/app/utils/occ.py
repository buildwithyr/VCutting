"""Duenne Schicht ueber OpenCascade (OCP).

OCP 8 hat die NCollection-Klassen von ``OCP.TColgp``/``OCP.TColStd`` nach
``OCP.collections`` verschoben. Diese Datei kapselt den Unterschied, damit der
restliche Code nur eine Schreibweise kennt.
"""

from __future__ import annotations

import numpy as np

try:  # OCP >= 8
    from OCP.collections import Array1_double as Array1OfReal
    from OCP.collections import Array1_gp_Pnt as Array1OfPnt
    from OCP.collections import Array1_int as Array1OfInteger
    from OCP.collections import (
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher,
    )

    IndexedDataMapOfShapeListOfShape = (
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher
    )
except ImportError:  # pragma: no cover - OCP 7 Fallback
    from OCP.TColgp import TColgp_Array1OfPnt as Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger as Array1OfInteger
    from OCP.TColStd import TColStd_Array1OfReal as Array1OfReal
    from OCP.TopTools import (
        TopTools_IndexedDataMapOfShapeListOfShape as IndexedDataMapOfShapeListOfShape,
    )

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.gp import gp_Pnt
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Edge, TopoDS_Vertex

__all__ = [
    "Array1OfInteger",
    "Array1OfPnt",
    "Array1OfReal",
    "IndexedDataMapOfShapeListOfShape",
    "bbox_of",
    "edge_endpoints",
    "point_array",
]


def point_array(points: np.ndarray) -> Array1OfPnt:
    """Numpy Nx3 nach OCC-Punktarray (1-basiert)."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points muss die Form Nx3 haben.")
    array = Array1OfPnt(1, len(points))
    for index, (x, y, z) in enumerate(points, start=1):
        array.SetValue(index, gp_Pnt(float(x), float(y), float(z)))
    return array


def bbox_of(shape) -> tuple[float, float, float, float, float, float]:
    """Achsparallele Huelle als (xmin, ymin, zmin, xmax, ymax, zmax).

    ``Bnd_Box.Get()`` ist in OCP 8 nicht nutzbar, deshalb die Ecken.
    """
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    # OCC vergroessert die Huelle standardmaessig um einen Sicherheitsspalt.
    # Fuer Messungen und Pruefungen wollen wir die echten Werte.
    box.SetGap(0.0)
    if box.IsVoid():
        raise ValueError("Die Form hat keine Ausdehnung.")
    low, high = box.CornerMin(), box.CornerMax()
    return (low.X(), low.Y(), low.Z(), high.X(), high.Y(), high.Z())


def _as_edge(shape) -> TopoDS_Edge:
    """Casted eine allgemeine Form auf TopoDS_Edge.

    OCP 8 benennt die statischen Casts ``TopoDS.Edge``, OCP 7 ``TopoDS.Edge_s``.
    """
    if isinstance(shape, TopoDS_Edge):
        return shape
    cast = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    return cast(shape)


def edge_endpoints(edge) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Anfangs- und Endpunkt einer Kante."""
    first = TopoDS_Vertex()
    last = TopoDS_Vertex()
    TopExp.Vertices_s(_as_edge(edge), first, last)
    p0 = BRep_Tool.Pnt_s(first)
    p1 = BRep_Tool.Pnt_s(last)
    return (p0.X(), p0.Y(), p0.Z()), (p1.X(), p1.Y(), p1.Z())
