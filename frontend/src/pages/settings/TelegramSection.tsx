import { useEffect, useState } from "react";

import { useCreateTelegramLink, useDeleteTelegramLink, useMe } from "../../api/hooks";
import { Button } from "../../components/Button";
import { InlineError, QueryState } from "../../components/QueryState";
import { ApiError } from "../../lib/errors";
import { formatDateTime } from "../../lib/format";
import styles from "./settings.module.css";

export function TelegramSection() {
  const createLink = useCreateTelegramLink();
  const deleteLink = useDeleteTelegramLink();
  const link = createLink.data;
  const [now, setNow] = useState(() => Date.now());
  const waiting = link !== undefined && new Date(link.expires_at).getTime() > now;
  // Пока ссылка действует, ждём, когда пользователь нажмёт «Start» в Telegram.
  const me = useMe({ poll: waiting });
  const linked = me.data?.telegram_chat_id != null;

  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(timer);
  }, [waiting]);

  useEffect(() => {
    if (linked && link) createLink.reset();
  }, [linked, link, createLink]);

  const disabled = createLink.error instanceof ApiError && createLink.error.code === "telegram_disabled";

  return (
    <section id="telegram" className={styles.section} aria-labelledby="telegram-heading">
      <h2 id="telegram-heading">Telegram</h2>
      <p className={styles.lead}>
        Бот присылает вакансии с вердиктом «Откликаться», кнопки под сообщением меняют статус
        отклика.
      </p>
      <QueryState query={me} what="состояние привязки">
        {linked ? (
          <div className={styles.actions}>
            <span className={styles.badge}>Чат привязан</span>
            <Button variant="danger" busy={deleteLink.isPending} onClick={() => deleteLink.mutate()}>
              Отвязать чат
            </Button>
          </div>
        ) : waiting ? (
          <div className={styles.linkBox}>
            <a href={link.url} target="_blank" rel="noopener noreferrer">
              {link.url}
            </a>
            <span className="muted">
              Откройте ссылку и нажмите «Start». Ссылка одноразовая, действует до{" "}
              {formatDateTime(link.expires_at)}. Страница сама увидит привязку.
            </span>
          </div>
        ) : (
          <div className={styles.actions}>
            <Button variant="primary" busy={createLink.isPending} onClick={() => createLink.mutate()}>
              {link ? "Получить новую ссылку" : "Привязать чат"}
            </Button>
            {link && <span className="muted">Прошлая ссылка истекла.</span>}
          </div>
        )}
        {disabled ? (
          <p className={styles.warning}>
            Бот не настроен: задайте JOBRADAR_TELEGRAM__BOT_TOKEN в .env и пересоздайте контейнеры (docker compose up -d) — токен нужен API, воркеру и боту.
          </p>
        ) : (
          <InlineError error={createLink.error ?? deleteLink.error} />
        )}
      </QueryState>
    </section>
  );
}
