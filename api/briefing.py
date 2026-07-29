from __future__ import annotations

from typing import Literal, TypedDict

BriefingMode = Literal["short", "standard", "deep"]


class BriefingPreset(TypedDict):
    label: str
    description: str
    min_cards: int
    max_cards: int
    max_sources: int
    seconds_per_card: float
    max_tokens: int


BRIEFING_PRESETS: dict[BriefingMode, BriefingPreset] = {
    "short": {
        "label": "숏",
        "description": "핵심만 빠르게 전달하는 20~30초 브리핑",
        "min_cards": 6,
        "max_cards": 8,
        "max_sources": 8,
        "seconds_per_card": 3.5,
        "max_tokens": 4200,
    },
    "standard": {
        "label": "표준",
        "description": "배경·핵심 근거·영향을 갖춘 40~60초 브리핑",
        "min_cards": 10,
        "max_cards": 14,
        "max_sources": 16,
        "seconds_per_card": 4.0,
        "max_tokens": 7200,
    },
    "deep": {
        "label": "심층",
        "description": "맥락·쟁점·반론·전망까지 다루는 70~100초 브리핑",
        "min_cards": 16,
        "max_cards": 20,
        "max_sources": 24,
        "seconds_per_card": 4.5,
        "max_tokens": 11000,
    },
}


def get_briefing_preset(mode: BriefingMode | str) -> BriefingPreset:
    return BRIEFING_PRESETS.get(mode, BRIEFING_PRESETS["standard"])
