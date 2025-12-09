from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .base import ModelVariant, ModelVariantId, ModelFamilyId, ModelCapability


@dataclass(frozen=True)
class SegmentationModelVariant(ModelVariant):
    """
    Specialised view for segmentation models (e.g. SAM / SAM2).
    """

    def __init__(
        self,
        id: ModelVariantId,
        family_id: ModelFamilyId,
        display_name: str,
        min_vram_gb: float | None,
        metadata: Mapping[str, object],
    ) -> None:
        super().__init__(
            id=id,
            family_id=family_id,
            display_name=display_name,
            capabilities=ModelCapability.SEGMENTATION,
            min_vram_gb=min_vram_gb,
            metadata=metadata,
        )
