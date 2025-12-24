from __future__ import annotations

from typing import Any

from PySide6.QtGui import QImage


def numpy_rgb_to_qimage(rgb: Any) -> QImage:
    """
    Convert an HxWx3 uint8 RGB numpy array to a QImage (deep copy).

    This helper deliberately avoids importing numpy in the core canvas modules.
    It will raise a clear error if the input does not look like a numpy array.
    """
    try:
        h = int(rgb.shape[0])
        w = int(rgb.shape[1])
        channels = int(rgb.shape[2])
    except Exception as exc:  # pragma: no cover
        raise TypeError("rgb must be a numpy-like HxWx3 array") from exc

    if channels != 3:
        raise ValueError("rgb must have shape HxWx3")

    try:
        bytes_per_line = int(rgb.strides[0])
        img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        return img.copy()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Failed to create QImage from RGB array") from exc

