"""Журнал откликов: статусы без БД и сети."""

from typing import Literal, get_args

ApplicationStatus = Literal["new", "letter_ready", "applied", "invited", "rejected", "declined"]
APPLICATION_STATUSES: frozenset[str] = frozenset(get_args(ApplicationStatus))
# Кнопки бота меняют только эти статусы: нажатие в старом сообщении не должно откатить
# «пригласили» или «отказ», выставленные позже через API.
BUTTON_OVERRIDABLE: frozenset[str] = frozenset({"new", "letter_ready", "applied", "declined"})
