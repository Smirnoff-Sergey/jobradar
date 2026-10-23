// Короткие имена для типов из сгенерированной схемы API.
import type { components, operations } from "./schema";

type Schemas = components["schemas"];

export type ApplicationDetail = Schemas["ApplicationDetail"];
export type ApplicationListItem = Schemas["ApplicationListItem"];
export type ApplicationStatus = Schemas["ApplicationRead"]["status"];
export type ContractType = NonNullable<Schemas["SearchProfileUpdate"]["contract_types"]>[number];
export type Evaluation = Schemas["EvaluationRead"];
export type Letter = Schemas["LetterRead"];
export type LLMUsage = Schemas["LLMUsageRead"];
export type Resume = Schemas["ResumeRead"];
export type SearchProfile = Schemas["SearchProfileRead"];
export type SearchProfileUpdate = Schemas["SearchProfileUpdate"];
export type Source = Schemas["SourceRead"];
export type TaskStatus = Schemas["TaskStatusRead"];
export type User = Schemas["UserRead"];
export type Vacancy = Schemas["VacancyRead"];
export type VacancyListItem = Schemas["VacancyListItem"];
export type Verdict = NonNullable<Evaluation["verdict"]>;

export type VacancyQuery = NonNullable<operations["list_vacancies"]["parameters"]["query"]>;
export type ApplicationQuery = NonNullable<operations["list_applications"]["parameters"]["query"]>;
