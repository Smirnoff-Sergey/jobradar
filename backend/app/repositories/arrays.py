"""Условия «значение в списке» с массивом одним параметром.

`IN (...)` разворачивает список в отдельные параметры, а asyncpg принимает не больше 32767
параметров на запрос. `= ANY(:array)` передаёт весь список одним параметром-массивом.
"""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import ColumnElement, all_, any_, literal
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.types import TypeEngine


def in_array(
    column: InstrumentedAttribute[Any], values: Iterable[Any], item_type: TypeEngine[Any]
) -> ColumnElement[bool]:
    return column == any_(literal(list(values), ARRAY(item_type)))


def not_in_array(
    column: InstrumentedAttribute[Any], values: Iterable[Any], item_type: TypeEngine[Any]
) -> ColumnElement[bool]:
    return column != all_(literal(list(values), ARRAY(item_type)))
