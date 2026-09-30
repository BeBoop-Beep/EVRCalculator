"""Dependency-free JSON-Schema subset validator and fixture manifest for FMA V1.

The repository has no ``jsonschema`` dependency, so the Focused Market Activity
contract ships a small, strict validator for the keyword subset its schemas
use. Unsupported keywords are an error (a schema can never silently rely on a
keyword this validator ignores). Pure: file reads only, no network, no DB.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from backend.domain.pokemon.market_activity import canonical_json

SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$id", "$ref", "$defs", "$comment", "title", "description", "type", "enum", "const",
    "properties", "required", "additionalProperties", "items", "minimum", "maximum",
    "minItems", "maxItems", "minLength", "pattern", "oneOf", "anyOf", "format",
})
_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}
_DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class SchemaError(ValueError):
    pass


class SchemaRegistry:
    def __init__(self, schema_dir: Path) -> None:
        self.dir = Path(schema_dir)
        self.schemas: dict[str, dict[str, Any]] = {}
        for path in sorted(self.dir.glob("*.schema.json")):
            self.schemas[path.name] = json.loads(path.read_text(encoding="utf-8"))

    def resolve(self, ref: str, base: str) -> tuple[dict[str, Any], str]:
        file_part, _, pointer = ref.partition("#")
        name = file_part or base
        if name not in self.schemas:
            raise SchemaError(f"unknown schema reference {ref!r}")
        node: Any = self.schemas[name]
        for token in [t for t in pointer.split("/") if t]:
            node = node[token]
        return node, name

    def validate(self, instance: Any, schema_name: str) -> list[str]:
        errors: list[str] = []
        self._check(instance, self.schemas[schema_name], schema_name, "$", errors)
        return errors

    def _check(self, value: Any, schema: Mapping[str, Any], base: str, path: str, errors: list[str]) -> None:
        unknown = set(schema) - SUPPORTED_KEYWORDS
        if unknown:
            raise SchemaError(f"unsupported schema keyword(s) {sorted(unknown)} at {base}")
        if "$ref" in schema:
            target, target_base = self.resolve(schema["$ref"], base)
            self._check(value, target, target_base, path, errors)
            return
        kinds = schema.get("type")
        if kinds is not None:
            kinds = [kinds] if isinstance(kinds, str) else list(kinds)
            if not any(_TYPES[k](value) for k in kinds):
                errors.append(f"{path}: expected {kinds}, got {type(value).__name__}")
                return
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: expected const {schema['const']!r}")
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: {value!r} not in enum")
        if isinstance(value, str):
            if "pattern" in schema and not re.search(schema["pattern"], value):
                errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
            if len(value) < int(schema.get("minLength", 0)):
                errors.append(f"{path}: shorter than minLength")
            fmt = schema.get("format")
            if fmt == "date":
                try:
                    date.fromisoformat(value)
                except ValueError:
                    errors.append(f"{path}: invalid date {value!r}")
            elif fmt == "date-time" and not _DATE_TIME.match(value):
                errors.append(f"{path}: date-time must be UTC 'YYYY-MM-DDTHH:MM:SSZ'")
        if _TYPES["number"](value):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{path}: below minimum")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{path}: above maximum")
        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value:
                    errors.append(f"{path}: missing required {key!r}")
            props = schema.get("properties", {})
            extra = schema.get("additionalProperties", True)
            for key, item in value.items():
                if key in props:
                    self._check(item, props[key], base, f"{path}.{key}", errors)
                elif extra is False:
                    errors.append(f"{path}: unexpected property {key!r}")
                elif isinstance(extra, dict):
                    self._check(item, extra, base, f"{path}.{key}", errors)
        if isinstance(value, list):
            if len(value) < int(schema.get("minItems", 0)):
                errors.append(f"{path}: fewer than minItems")
            if "maxItems" in schema and len(value) > int(schema["maxItems"]):
                errors.append(f"{path}: more than maxItems")
            if "items" in schema:
                for index, item in enumerate(value):
                    self._check(item, schema["items"], base, f"{path}[{index}]", errors)
        for keyword in ("oneOf", "anyOf"):
            if keyword in schema:
                matches = 0
                for option in schema[keyword]:
                    sub: list[str] = []
                    self._check(value, option, base, path, sub)
                    matches += not sub
                if (keyword == "oneOf" and matches != 1) or (keyword == "anyOf" and matches < 1):
                    errors.append(f"{path}: {keyword} matched {matches} options")


def content_fingerprint(path: Path) -> str:
    """SHA-256 of canonical JSON: stable across CRLF/LF checkouts and key order."""
    return hashlib.sha256(canonical_json(json.loads(Path(path).read_text(encoding="utf-8"))).encode("ascii")).hexdigest()
