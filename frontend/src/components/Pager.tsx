import { plural } from "../lib/format";
import { PAGE_SIZE } from "../lib/queryParams";
import { Button } from "./Button";
import styles from "./Pager.module.css";

interface Props {
  page: number;
  total: number;
  onPage: (page: number) => void;
  /** Склонение после «из»: ["вакансии", "вакансий", "вакансий"]. */
  nouns: readonly [string, string, string];
}

/** Пагинация списка. Страница за концом списка (старая ссылка) — кнопка «На первую страницу». */
export function Pager({ page, total, onPage, nouns }: Props) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const go = (next: number) => {
    onPage(next);
    window.scrollTo({ top: 0 });
  };

  if (page > pages) {
    return (
      <nav className={styles.pager} aria-label="Страницы">
        <span>Страницы {page} нет.</span>
        <Button variant="secondary" onClick={() => go(1)}>
          На первую страницу
        </Button>
      </nav>
    );
  }

  const first = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const last = Math.min(page * PAGE_SIZE, total);
  return (
    <nav className={styles.pager} aria-label="Страницы">
      <span>
        {first}–{last} из {total} {plural(total, ...nouns)}
      </span>
      <div className={styles.buttons}>
        <Button variant="secondary" disabled={page <= 1} onClick={() => go(page - 1)}>
          Назад
        </Button>
        <Button variant="secondary" disabled={page >= pages} onClick={() => go(page + 1)}>
          Дальше
        </Button>
      </div>
    </nav>
  );
}
