import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { keys, useLetters, useRequestLetter } from "../api/hooks";
import type { Letter } from "../api/models";
import { copyText } from "../lib/clipboard";
import { ApiError } from "../lib/errors";
import { formatDateTime } from "../lib/format";
import { Button } from "./Button";
import styles from "./LetterPanel.module.css";
import panel from "./panel.module.css";
import { InlineError } from "./QueryState";

/** Черновик сопроводительного письма: только по фактам резюме, с цитатами-подтверждениями. */
export function LetterPanel({ vacancyId }: { vacancyId: number }) {
  const client = useQueryClient();
  const letters = useLetters(vacancyId);
  const request = useRequestLetter(vacancyId);
  const [latest, ...older] = letters.data ?? [];
  const writing = latest?.status === "pending";

  // Черновик дописан — статус отклика мог смениться на «письмо готово».
  const wasWriting = useRef(false);
  useEffect(() => {
    if (wasWriting.current && !writing) {
      void client.invalidateQueries({ queryKey: keys.vacancies });
      void client.invalidateQueries({ queryKey: keys.applications });
    }
    wasWriting.current = writing;
  }, [writing, client]);

  const llmDisabled =
    request.error instanceof ApiError && request.error.code === "llm_disabled";

  return (
    <section className={`${panel.panel} ${styles.panel}`} aria-labelledby="letter-heading">
      <div className={styles.header}>
        <h2 id="letter-heading">Письмо</h2>
        <Button
          variant={latest ? "secondary" : "primary"}
          busy={request.isPending || writing}
          onClick={() => request.mutate()}
        >
          {writing ? "Пишем черновик…" : latest ? "Написать заново" : "Написать письмо"}
        </Button>
      </div>

      {!latest && !letters.isPending && (
        <p className="muted">
          Черновик собирается из фактов вашего резюме. Под письмом — факты, на которые оно
          опирается, с дословными цитатами из резюме.
        </p>
      )}
      {llmDisabled ? (
        <p className="error-text" role="alert">
          Письма выключены: не задан ключ LLM (JOBRADAR_LLM__API_KEY).
        </p>
      ) : (
        <InlineError error={request.error ?? letters.error} />
      )}

      {latest && <LetterView letter={latest} isLatest />}

      {older.length > 0 && (
        <details className={styles.older}>
          <summary>Прошлые черновики: {older.length}</summary>
          {older.map((letter) => (
            <LetterView key={letter.id} letter={letter} />
          ))}
        </details>
      )}
    </section>
  );
}

function LetterView({ letter, isLatest = false }: { letter: Letter; isLatest?: boolean }) {
  if (letter.status === "pending") {
    return (
      <p className="muted" role="status">
        Модель пишет черновик. Обычно это занимает до минуты.
      </p>
    );
  }
  if (letter.status === "failed") {
    return (
      <p className="error-text" role={isLatest ? "alert" : undefined}>
        {formatDateTime(letter.created_at)}: черновик не получился. {letter.error}
      </p>
    );
  }
  return (
    <article className={styles.letter}>
      <div className={styles.textRow}>
        <p className={styles.text}>{letter.text}</p>
        <CopyButton text={letter.text ?? ""} />
      </div>
      {letter.facts && letter.facts.length > 0 && (
        <div>
          <h3 className={panel.subheading}>На чём основано</h3>
          <ul className={panel.evidence}>
            {letter.facts.map((fact, index) => (
              <li key={index}>
                <span>{fact.claim}</span>
                <q className={panel.proof}>{fact.resume_quote}</q>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="muted">
        {formatDateTime(letter.created_at)}, {letter.model ?? "модель не указана"}
      </p>
    </article>
  );
}

type CopyState = "idle" | "copied" | "failed";

function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState<CopyState>("idle");
  useEffect(() => {
    if (state === "idle") return;
    const timer = setTimeout(() => setState("idle"), 2500);
    return () => clearTimeout(timer);
  }, [state]);
  return (
    <span className={styles.copy}>
      <Button
        variant="quiet"
        onClick={() => {
          copyText(text).then(
            () => setState("copied"),
            () => setState("failed"),
          );
        }}
      >
        Скопировать
      </Button>
      <span role="status" className="muted">
        {state === "copied" ? "Скопировано" : state === "failed" ? "Выделите текст вручную" : ""}
      </span>
    </span>
  );
}
