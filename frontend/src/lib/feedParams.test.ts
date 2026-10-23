import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS, filtersToParams, filtersToQuery, parseFilters } from "./feedParams";

describe("parseFilters", () => {
  it("пустой адрес — фильтры по умолчанию", () => {
    expect(parseFilters(new URLSearchParams())).toEqual(DEFAULT_FILTERS);
  });

  it("читает все фильтры", () => {
    const params = new URLSearchParams(
      "status=all&verdict=apply&score_min=70&source=getmatch&application=applied&sort=score&page=3",
    );
    expect(parseFilters(params)).toEqual({
      status: "all",
      verdict: "apply",
      scoreMin: 70,
      source: "getmatch",
      applicationStatus: "applied",
      sort: "score",
      page: 3,
    });
  });

  it("неверные значения заменяются умолчаниями", () => {
    const params = new URLSearchParams("status=x&verdict=yes&score_min=101&sort=random&page=-2");
    expect(parseFilters(params)).toEqual(DEFAULT_FILTERS);
  });
});

describe("filtersToParams", () => {
  it("умолчания в адрес не пишутся", () => {
    expect(filtersToParams(DEFAULT_FILTERS).toString()).toBe("");
  });

  it("туда и обратно без потерь", () => {
    const filters = { ...DEFAULT_FILTERS, verdict: "maybe" as const, scoreMin: 40, page: 2 };
    expect(parseFilters(filtersToParams(filters))).toEqual(filters);
  });
});

describe("filtersToQuery", () => {
  it("страница превращается в смещение", () => {
    const query = filtersToQuery({ ...DEFAULT_FILTERS, page: 3 });
    expect(query).toMatchObject({ limit: 20, offset: 40, status: "passed", sort: "published" });
  });
});
