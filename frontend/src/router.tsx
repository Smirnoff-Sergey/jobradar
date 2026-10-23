import { createBrowserRouter } from "react-router";

import { AppLayout } from "./components/AppLayout";
import { RequireAuth } from "./components/RequireAuth";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { FeedPage } from "./pages/FeedPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SettingsPage } from "./pages/settings/SettingsPage";
import { VacancyPage } from "./pages/VacancyPage";

export const router = createBrowserRouter([
  { path: "/login", Component: LoginPage },
  {
    Component: RequireAuth,
    children: [
      {
        Component: AppLayout,
        children: [
          { index: true, Component: FeedPage },
          { path: "vacancies/:id", Component: VacancyPage },
          { path: "applications", Component: ApplicationsPage },
          { path: "settings", Component: SettingsPage },
          { path: "*", Component: NotFoundPage },
        ],
      },
    ],
  },
]);
