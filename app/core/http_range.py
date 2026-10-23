"""
Parser de la cabecera HTTP Range (RFC 9110, solo unidad `bytes` y un único rango).
"""
from typing import Optional, Tuple, Union

UNSATISFIABLE = "unsatisfiable"

RangeResult = Union[None, Tuple[int, int], str]


def parse_range(header: Optional[str], size: int) -> RangeResult:
    """
    Interpreta una cabecera Range para un recurso de `size` bytes.

    Args:
        header: Valor de la cabecera Range (o None)
        size: Tamaño total del recurso en bytes

    Returns:
        None si debe ignorarse y servir el recurso completo (sin cabecera, unidad
        distinta de bytes, varios rangos o sintaxis inválida); (inicio, fin) inclusivos
        y ya acotados al tamaño; o "unsatisfiable" si el rango no se puede cumplir (416).
    """
    if not header:
        return None

    unit, _, spec = header.partition("=")
    if unit.strip().lower() != "bytes" or "," in spec:
        return None

    start_s, dash, end_s = spec.strip().partition("-")
    if not dash:
        return None
    start_s, end_s = start_s.strip(), end_s.strip()

    try:
        if not start_s:  # sufijo: últimos N bytes
            if not end_s:
                return None
            suffix = int(end_s)
            if suffix <= 0 or size == 0:
                return UNSATISFIABLE
            return max(size - suffix, 0), size - 1

        start = int(start_s)
        end = int(end_s) if end_s else None
    except ValueError:
        return None

    if start < 0 or (end is not None and end < start):
        return None
    if start >= size:
        return UNSATISFIABLE
    return start, size - 1 if end is None else min(end, size - 1)
