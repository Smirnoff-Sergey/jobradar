// Подписи значений API для интерфейса. Совпадают с подписями Telegram-бота.
import type { ApplicationStatus, ContractType, Verdict } from "../api/models";

export const APPLICATION_STATUSES: readonly ApplicationStatus[] = [
  "new",
  "letter_ready",
  "applied",
  "invited",
  "rejected",
  "declined",
];

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  new: "Новый",
  letter_ready: "Письмо готово",
  applied: "Откликнулся",
  invited: "Пригласили",
  rejected: "Отказ",
  declined: "Не подходит",
};

export const VERDICTS: readonly Verdict[] = ["apply", "maybe", "skip"];

export const VERDICT_LABELS: Record<Verdict, string> = {
  apply: "Откликаться",
  maybe: "Подумать",
  skip: "Пропустить",
};

export const CONTRACT_TYPES: readonly ContractType[] = ["TK", "GPH", "IP", "SELF_EMPLOYED"];

export const CONTRACT_LABELS: Record<ContractType, string> = {
  TK: "ТК",
  GPH: "ГПХ",
  IP: "ИП",
  SELF_EMPLOYED: "Самозанятость",
};

const WORK_FORMAT_LABELS: Record<string, string> = {
  remote: "удалённо",
  hybrid: "гибрид",
  office: "офис",
  relocation: "релокация",
};

/** Неизвестное значение показывается как есть: источник может добавить новое. */
export function contractLabel(value: string): string {
  return value in CONTRACT_LABELS ? CONTRACT_LABELS[value as ContractType] : value;
}

export function workFormatLabel(value: string): string {
  return WORK_FORMAT_LABELS[value] ?? value;
}
