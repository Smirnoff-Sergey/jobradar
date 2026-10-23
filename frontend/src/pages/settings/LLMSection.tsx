import { useState } from "react";

import { useLLMUsage } from "../../api/hooks";
import { QueryState } from "../../components/QueryState";
import { formatDateTime } from "../../lib/format";
import styles from "./settings.module.css";

export function LLMSection() {
  const usage = useLLMUsage();
  const data = usage.data;
  // Время открытия страницы: истёкшая пауза не показывается.
  const [now] = useState(() => Date.now());
  const pausedUntil = data?.paused_until ? new Date(data.paused_until) : null;
  const paused = pausedUntil !== null && pausedUntil.getTime() > now;
  // После платного ответа backend ставит паузу до 9999 года — то есть до ручного снятия.
  const indefinite = pausedUntil !== null && pausedUntil.getFullYear() >= 9000;
  return (
    <section id="llm" className={styles.section} aria-labelledby="llm-heading">
      <h2 id="llm-heading">Оценка</h2>
      <p className={styles.lead}>
        Вакансии оценивают только бесплатные модели OpenRouter. Когда дневной лимит исчерпан,
        оценка продолжится на следующие сутки (по UTC).
      </p>
      <QueryState query={usage} what="лимит оценки">
        {data && (
          <>
            {!data.enabled && (
              <p className={styles.warning}>
                Оценка выключена: не задан ключ JOBRADAR_LLM__API_KEY.
              </p>
            )}
            {paused && data.paused_until && (
              <p className={styles.warning}>
                {indefinite
                  ? "Оценка остановлена до ручного снятия"
                  : `Оценка остановлена до ${formatDateTime(data.paused_until)}`}
                {data.pause_reason && `: ${data.pause_reason}`}. Снять остановку —{" "}
                <code>python -m app.cli llm-unpause</code>.
              </p>
            )}
            <dl className={styles.stats}>
              <dt>Запросов сегодня</dt>
              <dd>
                {data.used} из {data.limit}
              </dd>
              <dt>Модели</dt>
              <dd>{data.models.length > 0 ? data.models.join(", ") : "не заданы"}</dd>
            </dl>
          </>
        )}
      </QueryState>
    </section>
  );
}
