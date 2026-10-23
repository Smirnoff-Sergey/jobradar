import { useQueryClient } from "@tanstack/react-query";
import { type SubmitEvent, useState } from "react";

import { keys, useBackgroundTask, useSaveSearchProfile, useSearchProfile } from "../../api/hooks";
import type { ContractType, SearchProfile } from "../../api/models";
import { Button } from "../../components/Button";
import { InlineError, QueryState } from "../../components/QueryState";
import { fieldErrors } from "../../lib/errors";
import { CONTRACT_LABELS, CONTRACT_TYPES } from "../../lib/labels";
import { formatList, parseList } from "../../lib/lists";
import { isTaskFailed } from "../../lib/tasks";
import styles from "./settings.module.css";

export function ProfileSection() {
  const profile = useSearchProfile();
  return (
    <section id="profile" className={styles.section} aria-labelledby="profile-heading">
      <h2 id="profile-heading">Критерии поиска</h2>
      <p className={styles.lead}>
        Фильтр отсеивает вакансии до оценки моделью: так дневной лимит запросов тратится только на
        подходящие.
      </p>
      <QueryState query={profile} what="критерии поиска">
        {profile.data && <ProfileForm profile={profile.data} />}
      </QueryState>
    </section>
  );
}

function ProfileForm({ profile }: { profile: SearchProfile }) {
  const client = useQueryClient();
  const [keywords, setKeywords] = useState(formatList(profile.title_keywords));
  const [stopWords, setStopWords] = useState(formatList(profile.stop_words));
  const [minSalary, setMinSalary] = useState(profile.min_salary?.toString() ?? "");
  const [salaryIsNet, setSalaryIsNet] = useState(profile.min_salary_is_net);
  const [remoteOnly, setRemoteOnly] = useState(profile.remote_only);
  const [contracts, setContracts] = useState<ContractType[]>(profile.contract_types);

  const save = useSaveSearchProfile();
  const refilter = useBackgroundTask(() => {
    void client.invalidateQueries({ queryKey: keys.vacancies });
  });
  const errors = fieldErrors(save.error);

  const onSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    save.mutate(
      {
        title_keywords: parseList(keywords),
        stop_words: parseList(stopWords),
        min_salary: minSalary === "" ? null : Number(minSalary),
        min_salary_is_net: salaryIsNet,
        remote_only: remoteOnly,
        contract_types: contracts,
      },
      { onSuccess: (result) => refilter.start(result.refilter_task_id) },
    );
  };

  const toggleContract = (type: ContractType, checked: boolean) => {
    setContracts((current) =>
      checked ? CONTRACT_TYPES.filter((t) => t === type || current.includes(t)) : current.filter((t) => t !== type),
    );
  };

  return (
    <form className={styles.form} onSubmit={onSubmit}>
      <div className={styles.row}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Слова в названии</span>
          <textarea
            rows={4}
            value={keywords}
            onChange={(event) => setKeywords(event.target.value)}
            aria-invalid={Boolean(errors.title_keywords) || undefined}
          />
          <span className={styles.hint}>По одному в строке. Пусто — подходит любое название.</span>
          {errors.title_keywords && <span className="error-text">{errors.title_keywords}</span>}
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Стоп-слова</span>
          <textarea
            rows={4}
            value={stopWords}
            onChange={(event) => setStopWords(event.target.value)}
            aria-invalid={Boolean(errors.stop_words) || undefined}
          />
          <span className={styles.hint}>Ищутся в названии, компании и кратком описании.</span>
          {errors.stop_words && <span className="error-text">{errors.stop_words}</span>}
        </label>
      </div>

      <div className={styles.row}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Зарплата от, ₽</span>
          <input
            type="number"
            min={0}
            step={1000}
            inputMode="numeric"
            value={minSalary}
            onChange={(event) => setMinSalary(event.target.value)}
            aria-invalid={Boolean(errors.min_salary) || undefined}
          />
          <span className={styles.hint}>
            Пусто — без порога. Вакансии без зарплаты в рублях фильтр пропускает.
          </span>
          {errors.min_salary && <span className="error-text">{errors.min_salary}</span>}
        </label>
        <div className={styles.field}>
          <span className={styles.fieldLabel}>Условия</span>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={salaryIsNet}
              onChange={(event) => setSalaryIsNet(event.target.checked)}
            />
            Порог зарплаты — на руки
          </label>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={remoteOnly}
              onChange={(event) => setRemoteOnly(event.target.checked)}
            />
            Только удалённая работа
          </label>
        </div>
      </div>

      <fieldset className={styles.checks}>
        <legend>Оформление</legend>
        {CONTRACT_TYPES.map((type) => (
          <label key={type} className={styles.check}>
            <input
              type="checkbox"
              checked={contracts.includes(type)}
              onChange={(event) => toggleContract(type, event.target.checked)}
            />
            {CONTRACT_LABELS[type]}
          </label>
        ))}
      </fieldset>
      <p className={styles.hint}>
        Ничего не отмечено — любое оформление. Если источник не сообщает тип договора (getmatch),
        вакансия не отсеивается.
      </p>

      <div className={styles.actions}>
        <Button type="submit" variant="primary" busy={save.isPending}>
          Сохранить критерии
        </Button>
        {refilter.running && <span className="muted">Перефильтровываем вакансии…</span>}
        {refilter.task?.state === "SUCCESS" && (
          <span className={styles.success}>Критерии сохранены, лента обновлена</span>
        )}
      </div>
      {Object.keys(errors).length === 0 && <InlineError error={save.error} />}
      {isTaskFailed(refilter.task) && (
        <p className="error-text" role="alert">
          Критерии сохранены, но перефильтровка не удалась. Сохраните критерии ещё раз, чтобы повторить её.
        </p>
      )}
    </form>
  );
}
