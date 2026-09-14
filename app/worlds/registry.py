"""Validated loader and lookup registry for declarative world packs."""

import re
import unicodedata
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from app.worlds.models import (
    WorldCatalogResponse,
    WorldClassDefinition,
    WorldPack,
    WorldPackReference,
    WorldPackSummary,
)


PACKS_DIR = Path(__file__).resolve().parent / "packs"
DEFAULT_WORLD_ID = "dark_fantasy"
DEFAULT_WORLD_VERSION = 1


class WorldPackNotFoundError(LookupError):
    pass


def _normalized(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize(
            "NFKD",
            value.casefold().translate(str.maketrans({"ł": "l"})),
        )
        if not unicodedata.combining(character)
    )


class WorldPackRegistry:
    def __init__(
        self,
        packs: tuple[WorldPack, ...],
        *,
        default_world_id: str,
        default_world_version: int,
    ) -> None:
        indexed: dict[tuple[str, int], WorldPack] = {}
        for pack in packs:
            key = (pack.id, pack.version)
            if key in indexed:
                raise ValueError(f"duplicate world pack: {pack.key}")
            indexed[key] = pack
        default_key = (default_world_id, default_world_version)
        if default_key not in indexed:
            raise ValueError(
                f"default world pack is not registered: {default_world_id}@{default_world_version}"
            )
        self._packs: Mapping[tuple[str, int], WorldPack] = MappingProxyType(indexed)
        self._default_key = default_key

    @classmethod
    def from_directory(cls, directory: Path) -> "WorldPackRegistry":
        packs_list: list[WorldPack] = []
        for path in sorted(directory.glob("*.json")):
            pack = WorldPack.model_validate_json(path.read_text(encoding="utf-8"))
            expected_filename = f"{pack.id}_v{pack.version}.json"
            if path.name != expected_filename:
                raise ValueError(
                    f"world pack filename must be {expected_filename}, got {path.name}"
                )
            packs_list.append(pack)
        packs = tuple(packs_list)
        if not packs:
            raise ValueError(f"no world packs found in {directory}")
        return cls(
            packs,
            default_world_id=DEFAULT_WORLD_ID,
            default_world_version=DEFAULT_WORLD_VERSION,
        )

    @property
    def default(self) -> WorldPack:
        return self._packs[self._default_key]

    def get(self, world_id: str | None = None, version: int | None = None) -> WorldPack:
        if world_id is None and version is None:
            return self.default
        if world_id is None or version is None:
            raise WorldPackNotFoundError("world id and version must be provided together")
        try:
            return self._packs[(world_id, version)]
        except KeyError as error:
            raise WorldPackNotFoundError(f"unknown world pack: {world_id}@{version}") from error

    def list(self) -> tuple[WorldPack, ...]:
        return tuple(self._packs[key] for key in sorted(self._packs))

    def catalog(self) -> WorldCatalogResponse:
        default = self.default
        return WorldCatalogResponse(
            default_world=WorldPackReference(
                id=default.id,
                version=default.version,
                key=default.key,
            ),
            worlds=tuple(WorldPackSummary.from_pack(pack) for pack in self.list()),
        )

    def resolve_class(self, pack: WorldPack, value: str) -> WorldClassDefinition:
        normalized_value = _normalized(value)
        words = re.findall(r"[a-z0-9_]+", normalized_value)
        for class_definition in pack.classes:
            candidates = (class_definition.id, class_definition.name, *class_definition.aliases)
            if any(
                normalized_value == _normalized(candidate)
                or any(word.startswith(_normalized(candidate)) for word in words)
                for candidate in candidates
            ):
                return class_definition
        return next(
            class_definition
            for class_definition in pack.classes
            if class_definition.id == pack.fallback_class_id
        )


WORLD_PACK_REGISTRY = WorldPackRegistry.from_directory(PACKS_DIR)


def get_default_world_pack() -> WorldPack:
    """Return the one controlled legacy fallback used before campaign persistence."""

    return WORLD_PACK_REGISTRY.default
