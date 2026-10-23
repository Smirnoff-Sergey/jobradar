/** Копирует текст в буфер обмена. На http-стенде (не secure context) Clipboard API нет —
 * тогда старый способ через скрытое поле и execCommand. */
export async function copyText(text: string): Promise<void> {
  if (window.isSecureContext && "clipboard" in navigator) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.append(field);
  field.select();
  try {
    // execCommand устарел, но это единственный способ без secure context.
    // eslint-disable-next-line @typescript-eslint/no-deprecated
    if (!document.execCommand("copy")) throw new Error("Копирование не поддерживается");
  } finally {
    field.remove();
  }
}
