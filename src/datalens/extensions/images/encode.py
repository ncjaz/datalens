from __future__ import annotations

"""
Small image encoding helpers (V2).

Intent:
- Reuse encoding logic across plugins (capture/export/import) without pulling Qt into the stack.
- Keep this module tiny and dependency-light. Pillow and NumPy are already project deps.

Conventions:
- Functions accept numpy-like arrays (H x W x C).
- `color_order` describes the input array channel order for 3/4-channel images.
"""

from io import BytesIO
from typing import TYPE_CHECKING, Literal

from PIL import Image

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    ArrayU8 = NDArray[np.uint8]
else:  # pragma: no cover - typing only
    ArrayU8 = object

ColorOrder = Literal["rgb", "bgr"]


def _to_pil_image(arr: ArrayU8, *, color_order: ColorOrder) -> Image.Image:
    # Pillow expects RGB(A) ordering for multi-channel images.
    import numpy as np

    a = np.asarray(arr)
    if a.dtype != np.uint8:
        a = a.astype(np.uint8, copy=False)

    if a.ndim == 2:
        return Image.fromarray(a, mode="L")

    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise ValueError(f"Expected HxW, HxWx3, or HxWx4 uint8 array; got shape={getattr(a, 'shape', None)}")

    if color_order == "bgr":
        a = a[..., ::-1]

    if a.shape[2] == 3:
        return Image.fromarray(a, mode="RGB")
    return Image.fromarray(a, mode="RGBA")


def encode_jpeg(arr: ArrayU8, *, quality: int = 92, color_order: ColorOrder = "rgb") -> bytes:
    """
    Encode a uint8 image as JPEG and return the bytes.
    """
    img = _to_pil_image(arr, color_order=color_order)
    buf = BytesIO()
    q = int(quality)
    if q < 1:
        q = 1
    if q > 95:
        q = 95
    img.save(buf, format="JPEG", quality=q, optimize=True)
    return buf.getvalue()


def encode_png(arr: ArrayU8, *, compress_level: int = 6, color_order: ColorOrder = "rgb") -> bytes:
    """
    Encode a uint8 image as PNG and return the bytes.
    """
    img = _to_pil_image(arr, color_order=color_order)
    buf = BytesIO()
    level = int(compress_level)
    if level < 0:
        level = 0
    if level > 9:
        level = 9
    img.save(buf, format="PNG", compress_level=level)
    return buf.getvalue()

