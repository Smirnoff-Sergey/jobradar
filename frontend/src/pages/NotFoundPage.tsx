import { Link } from "react-router";

import { EmptyState } from "../components/QueryState";

export function NotFoundPage() {
  return (
    <EmptyState title="Такой страницы нет">
      Вернитесь в <Link to="/">ленту вакансий</Link>.
    </EmptyState>
  );
}
