from __future__ import annotations

from dataclasses import dataclass
from enum import Flag, auto
from typing import Mapping, NewType

ModelFamilyId = NewType("ModelFamilyId", str)
ModelVariantId = NewType("ModelVariantId", str)


class ModelCapability(Flag):
    """
    Capabilities exposed by a model variant.

    Mirrors & simplifies what you had in V1: detection, segmentation,
    training, prompts, etc.
    """

    NONE = 0
    DETECTION = auto()
    SEGMENTATION = auto()
    TRAINING = auto()
    POINT_PROMPT = auto()
    BOX_PROMPT = auto()

    ALL = DETECTION | SEGMENTATION | TRAINING | POINT_PROMPT | BOX_PROMPT


@dataclass(frozen=True)
class ModelFamily:
    """
    High-level grouping: e.g. 'YOLO', 'SAM', 'RT-DETR'.
    """

    id: ModelFamilyId
    name: str
    description: str


@dataclass(frozen=True)
class ModelVariant:
    """
    Concrete model variant: e.g. 'yolov11n-detection', 'sam2-base'.

    `metadata` is a generic mapping for plugin/runtime-specific hints
    (weights path, HF model ID, image size, etc.).
    """

    id: ModelVariantId
    family_id: ModelFamilyId
    display_name: str
    capabilities: ModelCapability
    min_vram_gb: float | None
    metadata: Mapping[str, object]
