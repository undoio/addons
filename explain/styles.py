"""
Genuine People Personalities for the "explain" command.
"""

import pydantic

from . import assets


class Style(pydantic.BaseModel):
    description: str
    prompt: str


class _StyleDatabase(pydantic.RootModel[dict[str, Style]]):
    ...


STYLES = _StyleDatabase.model_validate_json(assets.STYLE_DEFINITIONS)


def names() -> list[str]:
    return list(STYLES.root.keys())


def get(name: str) -> Style | None:
    return STYLES.root.get(name)
