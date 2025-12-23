from __future__ import annotations

"""
Frame / image runtime contracts (V2).

These are **device-agnostic** data containers used for passing an in-memory
image (and optional extras like depth + intrinsics) between services/plugins.

They are intentionally Qt-free and can be used by:
- Capture plugin (webcam, RealSense, future SDKs)
- Annotation/review/model plugins (display + analysis)
- Streaming/capability providers (latest-frame pull)

Do not mix these with the project media index records (`MediaFileRecord`) which
represent on-disk files. A FrameBundle may *optionally* be associated with a
registered media record after saving, but it is first and foremost an in-memory
container.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from datalens.domain.system.media_index import MediaId

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    RgbArray = NDArray[np.uint8]
    DepthArray = NDArray[np.uint16] | NDArray[np.float32]
else:  # pragma: no cover - typing only
    RgbArray = object
    DepthArray = object


@dataclass(frozen=True, slots=True)
class CameraIntrinsics:
    """
    Minimal camera intrinsics (pinhole model).

    Notes:
    - Distortion coefficients/model are optional and SDK-specific.
    - For webcams, intrinsics are often unknown (set to None at FrameBundle).
    """

    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    distortion_model: str | None = None
    distortion_coeffs: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class FrameBundle:
    """
    In-memory representation of a single captured/loaded frame.

    `rgb` is the primary payload and should usually be present.
    `depth` and `intrinsics` are optional and may be None depending on source.
    """

    rgb: RgbArray
    timestamp_s: float
    source_id: str

    depth: DepthArray | None = None
    intrinsics: CameraIntrinsics | None = None
    depth_intrinsics: CameraIntrinsics | None = None

    # Optional linkage to the project media index after saving/registration.
    media_id: MediaId | None = None
    saved_relative_path: str | None = None

    @property
    def has_depth(self) -> bool:
        return self.depth is not None
