from __future__ import annotations

from typing import Any


def validate_params(schema: dict[str, Any], params: dict[str, Any]) -> list[dict[str, str]]:
    """Validate the small JSON Schema subset exposed by the action registry."""
    errors: list[dict[str, str]] = []
    _validate_object(schema, params, "", errors)
    return errors


def _validate_object(
    schema: dict[str, Any],
    params: dict[str, Any],
    prefix: str,
    errors: list[dict[str, str]],
) -> None:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    for name in sorted(required):
        field = _field_name(prefix, name)
        if name not in params or _is_empty_required(params[name]):
            errors.append({"field": field, "code": "required", "message": f"{field} is required"})

    if schema.get("additionalProperties") is False:
        for name in sorted(set(params) - set(properties)):
            field = _field_name(prefix, name)
            errors.append({"field": field, "code": "unknown", "message": f"unknown parameter: {field}"})

    for name, value in params.items():
        field_schema = properties.get(name)
        if not field_schema or value is None:
            continue
        field = _field_name(prefix, name)
        expected = field_schema.get("type", "string")
        if not _matches_type(value, expected):
            errors.append(
                {
                    "field": field,
                    "code": "type",
                    "message": f"{field} must be {expected}",
                }
            )
            continue
        enum = field_schema.get("enum")
        if enum and value not in enum:
            errors.append(
                {
                    "field": field,
                    "code": "enum",
                    "message": f"{field} must be one of: {', '.join(map(str, enum))}",
                }
            )
        if isinstance(value, str) and len(value) < int(field_schema.get("minLength", 0)):
            errors.append({"field": field, "code": "minLength", "message": f"{field} is too short"})
        if isinstance(value, int) and not isinstance(value, bool):
            minimum = field_schema.get("minimum")
            maximum = field_schema.get("maximum")
            if minimum is not None and value < minimum:
                errors.append({"field": field, "code": "minimum", "message": f"{field} must be >= {minimum}"})
            if maximum is not None and value > maximum:
                errors.append({"field": field, "code": "maximum", "message": f"{field} must be <= {maximum}"})
        if expected == "object" and isinstance(value, dict):
            _validate_object(field_schema, value, field, errors)


def _field_name(prefix: str, name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


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
