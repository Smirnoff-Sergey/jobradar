import { type SubmitEvent, useState } from "react";

import { useCreateResume, useResumes, useUpdateResume } from "../../api/hooks";
import type { Resume } from "../../api/models";
import { Button } from "../../components/Button";
import { EmptyState, InlineError, QueryState } from "../../components/QueryState";
import { fieldErrors } from "../../lib/errors";
import { formatDateTime } from "../../lib/format";
import styles from "./settings.module.css";

const TEXT_MIN = 50;

export function ResumeSection() {
  const resumes = useResumes();
  const [creating, setCreating] = useState(false);
  const active = resumes.data?.find((resume) => resume.is_active);
  const others = resumes.data?.filter((resume) => !resume.is_active) ?? [];

  return (
    <section id="resume" className={styles.section} aria-labelledby="resume-heading">
      <h2 id="resume-heading">Резюме</h2>
      <p className={styles.lead}>
        Вакансии оцениваются по активному резюме. Пишите в нём только реальный опыт: модель
        сравнивает требования с этим текстом.
      </p>
      <QueryState query={resumes} what="резюме">
        {active ? (
          <ResumeForm key={active.id} resume={active} />
        ) : (
          !creating && (
            <EmptyState title="Активного резюме нет">
              Без него вакансии не оцениваются. Добавьте резюме или сделайте активным одно из
              сохранённых.
            </EmptyState>
          )
        )}
        {others.length > 0 && <OtherResumes resumes={others} />}
        {creating ? (
          <ResumeForm onDone={() => setCreating(false)} />
        ) : (
          <div>
            <Button variant="secondary" onClick={() => setCreating(true)}>
              Добавить резюме
            </Button>
          </div>
        )}
      </QueryState>
    </section>
  );
}

function OtherResumes({ resumes }: { resumes: Resume[] }) {
  const update = useUpdateResume();
  return (
    <div className={styles.field}>
      <h3>Сохранённые</h3>
      <ul className={styles.list}>
        {resumes.map((resume) => (
          <li key={resume.id}>
            <span className={styles.itemMain}>
              {resume.title}
              <span className="muted">изменено {formatDateTime(resume.updated_at)}</span>
            </span>
            <Button
              variant="quiet"
              busy={update.isPending && update.variables.id === resume.id}
              onClick={() => update.mutate({ id: resume.id, is_active: true })}
            >
              Сделать активным
            </Button>
          </li>
        ))}
      </ul>
      <InlineError error={update.error} />
    </div>
  );
}

interface FormProps {
  /** Нет резюме — форма создаёт новое. */
  resume?: Resume;
  onDone?: () => void;
}

function ResumeForm({ resume, onDone }: FormProps) {
  const [title, setTitle] = useState(resume?.title ?? "");
  const [text, setText] = useState(resume?.text ?? "");
  const [saved, setSaved] = useState(false);
  const create = useCreateResume();
  const update = useUpdateResume();
  const mutation = resume ? update : create;
  const errors = fieldErrors(mutation.error);
  const textChanged = resume !== undefined && text !== resume.text;
  const dirty = resume === undefined || title !== resume.title || textChanged;

  const onSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaved(false);
    const onSuccess = () => {
      setSaved(true);
      onDone?.();
    };
    if (resume) update.mutate({ id: resume.id, title, text }, { onSuccess });
    else create.mutate({ title, text }, { onSuccess });
  };

  return (
    <form className={styles.form} onSubmit={onSubmit}>
      {!resume && <h3>Новое резюме</h3>}
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Название</span>
        <input
          type="text"
          required
          maxLength={200}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          aria-invalid={Boolean(errors.title) || undefined}
        />
        {errors.title && <span className="error-text">{errors.title}</span>}
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Текст</span>
        <textarea
          rows={14}
          required
          minLength={TEXT_MIN}
          maxLength={50_000}
          value={text}
          onChange={(event) => setText(event.target.value)}
          aria-invalid={Boolean(errors.text) || undefined}
        />
        <span className={styles.hint}>
          {text.length.toLocaleString("ru-RU")} знаков, нужно не меньше {TEXT_MIN}.
        </span>
        {errors.text && <span className="error-text">{errors.text}</span>}
      </label>
      {textChanged && (
        <p className={styles.warning}>
          После сохранения оценки по этому резюме удалятся и пересчитаются в пределах дневного
          лимита.
        </p>
      )}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" busy={mutation.isPending} disabled={!dirty}>
          {resume ? "Сохранить резюме" : "Добавить и сделать активным"}
        </Button>
        {onDone && (
          <Button variant="quiet" onClick={onDone}>
            Отмена
          </Button>
        )}
        {saved && !dirty && <span className={styles.success}>Резюме сохранено</span>}
      </div>
      {Object.keys(errors).length === 0 && <InlineError error={mutation.error} />}
    </form>
  );
}
