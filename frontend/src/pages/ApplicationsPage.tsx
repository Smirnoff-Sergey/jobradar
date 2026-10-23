import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { useApplication, useApplications, useUpdateApplication } from "../api/hooks";
import type { ApplicationListItem } from "../api/models";
import { Button } from "../components/Button";
import { Pager } from "../components/Pager";
import { EmptyState, InlineError, QueryState } from "../components/QueryState";
import rows from "../components/rows.module.css";
import { Select } from "../components/Select";
import { StatusPicker } from "../components/StatusPicker";
import { StatusPill } from "../components/StatusPill";
import { formatDateTime } from "../lib/format";
import { APPLICATION_STATUSES, APPLICATION_STATUS_LABELS } from "../lib/labels";
import { oneOf, PAGE_SIZE, pageOffset, parsePage } from "../lib/queryParams";
import { optionsFrom } from "../lib/options";
import styles from "./ApplicationsPage.module.css";

const STATUS_OPTIONS = optionsFrom(APPLICATION_STATUSES, APPLICATION_STATUS_LABELS, "Все");

export function ApplicationsPage() {
  const [params, setParams] = useSearchParams();
  const status = oneOf(params.get("status"), APPLICATION_STATUSES);
  const page = parsePage(params.get("page"));
  const applications = useApplications({ status, limit: PAGE_SIZE, offset: pageOffset(page) });
  const [openId, setOpenId] = useState<number | null>(null);

  const setQuery = (nextStatus: typeof status, nextPage: number) => {
    const query = new URLSearchParams();
    if (nextStatus) query.set("status", nextStatus);
    if (nextPage > 1) query.set("page", String(nextPage));
    setParams(query);
  };
  const data = applications.data;

  return (
    <div className={styles.page}>
      <div className={styles.heading}>
        <h1>Отклики</h1>
        <div className={styles.filter}>
          <Select
            label="Статус"
            value={status ?? ""}
            onChange={(value) => setQuery(value || null, 1)}
            options={STATUS_OPTIONS}
          />
        </div>
      </div>

      <QueryState query={applications} what="журнал откликов">
        {data?.total === 0 && (
          <EmptyState title={status ? "С таким статусом откликов нет" : "Откликов пока нет"}>
            Статус отклика ставится в карточке вакансии или кнопками в Telegram.
          </EmptyState>
        )}
        {data && data.total > 0 && (
          <>
            {data.items.length > 0 && (
              <ul className={rows.list} aria-busy={applications.isPlaceholderData || undefined}>
                {data.items.map((item) => (
                  <ApplicationRow
                    key={item.id}
                    item={item}
                    open={openId === item.id}
                    onToggle={() => setOpenId(openId === item.id ? null : item.id)}
                  />
                ))}
              </ul>
            )}
            <Pager
              page={page}
              total={data.total}
              onPage={(next) => setQuery(status, next)}
              nouns={["отклика", "откликов", "откликов"]}
            />
          </>
        )}
      </QueryState>
    </div>
  );
}

interface RowProps {
  item: ApplicationListItem;
  open: boolean;
  onToggle: () => void;
}

function ApplicationRow({ item, open, onToggle }: RowProps) {
  const detailsId = `application-${item.id}`;
  return (
    <li className={`${rows.row} ${styles.row}`}>
      <div className={styles.summary}>
        <div className={styles.vacancy}>
          <Link to={`/vacancies/${item.vacancy.id}`} className={`${rows.title} ${styles.title}`}>
            {item.vacancy.title}
          </Link>
          <span className="muted">
            {item.vacancy.company ?? "компания не указана"}
            {!item.vacancy.is_active && ", снята с публикации"}
          </span>
        </div>
        <StatusPill status={item.status} />
        <span className={`muted ${styles.date}`}>{formatDateTime(item.updated_at)}</span>
        <Button variant="quiet" aria-expanded={open} aria-controls={detailsId} onClick={onToggle}>
          {open ? "Свернуть" : "Подробнее"}
        </Button>
      </div>
      {item.notes && !open && <p className={styles.notesPreview}>{item.notes}</p>}
      {open && <ApplicationDetails id={item.id} domId={detailsId} />}
    </li>
  );
}

function ApplicationDetails({ id, domId }: { id: number; domId: string }) {
  const detail = useApplication(id);
  const update = useUpdateApplication(id);
  const [notes, setNotes] = useState<string | null>(null);
  const notesId = `${domId}-notes`;

  return (
    <div id={domId} className={styles.details}>
      <QueryState query={detail} what="историю отклика">
        {detail.data && (
          <>
            <div className={styles.section}>
              <h3>Статус</h3>
              <StatusPicker
                label="Статус отклика"
                value={detail.data.status}
                disabled={update.isPending}
                onChange={(status) => update.mutate({ status })}
              />
            </div>

            <form
              className={styles.section}
              onSubmit={(event) => {
                event.preventDefault();
                if (notes !== null) update.mutate({ notes }, { onSuccess: () => setNotes(null) });
              }}
            >
              <h3 id={`${notesId}-label`}>Заметки</h3>
              <textarea
                id={notesId}
                aria-labelledby={`${notesId}-label`}
                rows={3}
                maxLength={10_000}
                value={notes ?? detail.data.notes ?? ""}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="С кем говорили, что ответили, когда напомнить"
              />
              <div>
                <Button
                  type="submit"
                  variant="secondary"
                  busy={update.isPending}
                  disabled={notes === null}
                >
                  Сохранить заметки
                </Button>
              </div>
            </form>
            <InlineError error={update.error} />

            <div className={styles.section}>
              <h3>История</h3>
              <ol className={styles.history}>
                {detail.data.history.map((change, index) => (
                  <li key={index}>
                    <time dateTime={change.changed_at} className="muted">
                      {formatDateTime(change.changed_at)}
                    </time>
                    <span>
                      {change.from_status
                        ? `${APPLICATION_STATUS_LABELS[change.from_status]} → ${APPLICATION_STATUS_LABELS[change.to_status]}`
                        : `Создан: ${APPLICATION_STATUS_LABELS[change.to_status]}`}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          </>
        )}
      </QueryState>
    </div>
  );
}
