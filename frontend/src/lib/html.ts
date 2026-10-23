import DOMPurify from "dompurify";

// Описание приходит из источника HTML-разметкой. Чужой HTML выводится только после очистки:
// без скриптов, стилей, форм и картинок (картинки — это ещё и запросы на чужие сервера).
const OPTIONS = {
  FORBID_TAGS: ["style", "img", "form", "input", "button", "iframe"],
  FORBID_ATTR: ["style", "class", "id"],
};

DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer nofollow");
  }
});

export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, OPTIONS);
}
