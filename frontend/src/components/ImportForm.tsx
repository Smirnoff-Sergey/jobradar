import { type SubmitEvent, useState } from "react";
import { useNavigate } from "react-router";

import { useImportVacancy } from "../api/hooks";
import { Button } from "./Button";
import styles from "./ImportForm.module.css";
import { InlineError } from "./QueryState";

/** Добавить вакансию по ссылке на её страницу — сразу открывается её карточка. */
export function ImportForm() {
  const [url, setUrl] = useState("");
  const navigate = useNavigate();
  const importVacancy = useImportVacancy();

  const onSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    importVacancy.mutate(url.trim(), {
      onSuccess: (vacancy) => void navigate(`/vacancies/${vacancy.id}`),
    });
  };

  return (
    <form className={styles.form} onSubmit={onSubmit}>
      <label className={styles.field}>
        <span className="visually-hidden">Ссылка на вакансию</span>
        <input
          type="url"
          required
          maxLength={500}
          placeholder="Ссылка на вакансию getmatch.ru"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          aria-invalid={Boolean(importVacancy.error) || undefined}
          aria-describedby={importVacancy.error ? "import-error" : undefined}
        />
      </label>
      <Button type="submit" variant="secondary" busy={importVacancy.isPending}>
        {importVacancy.isPending ? "Добавляем…" : "Добавить"}
      </Button>
      {importVacancy.error != null && (
        <div className={styles.error}>
          <InlineError error={importVacancy.error} id="import-error" />
        </div>
      )}
    </form>
  );
}
