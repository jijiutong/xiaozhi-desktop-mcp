from __future__ import annotations

from typing import Any


def validate_params(schema: dict[str, Any], params: dict[str, Any]) -> list[dict[str, str]]:
    """Validate the small JSON Schema subset exposed by the action registry."""
    errors: list[dict[str, str]] = []
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    for name in sorted(required):
        if name not in params or _is_empty_required(params[name]):
            errors.append({"field": name, "code": "required", "message": f"{name} is required"})

    if schema.get("additionalProperties") is False:
        for name in sorted(set(params) - set(properties)):
            errors.append({"field": name, "code": "unknown", "message": f"unknown parameter: {name}"})

    for name, value in params.items():
        field_schema = properties.get(name)
        if not field_schema or value is None:
            continue
        expected = field_schema.get("type", "string")
        if not _matches_type(value, expected):
            errors.append(
                {
                    "field": name,
                    "code": "type",
                    "message": f"{name} must be {expected}",
                }
            )
            continue
        enum = field_schema.get("enum")
        if enum and value not in enum:
            errors.append(
                {
                    "field": name,
                    "code": "enum",
                    "message": f"{name} must be one of: {', '.join(map(str, enum))}",
                }
            )
    return errors


def _is_empty_required(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True
