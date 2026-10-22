from sqlalchemy import MetaData, text
from sqlalchemy.orm import DeclarativeBase

# Явные имена ограничений: Alembic генерирует предсказуемые миграции, а их можно удалять по имени.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Значение по умолчанию для колонок-массивов PostgreSQL.
EMPTY_ARRAY = text("'{}'")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
