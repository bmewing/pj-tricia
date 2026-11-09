from enum import StrEnum

from sqlalchemy import Enum


def string_enum[E: StrEnum](enum: type[E]) -> Enum:
    """Store a StrEnum as its values in a plain string column (no Postgres enum type)."""
    return Enum(
        enum,
        native_enum=False,
        length=16,
        values_callable=lambda members: [member.value for member in members],
    )
