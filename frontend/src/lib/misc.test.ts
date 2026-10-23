import { describe, expect, it } from "vitest";

import { contractLabel, workFormatLabel } from "./labels";
import { formatList, parseList } from "./lists";
import { optionsFrom } from "./options";
import { intInRange, oneOf, pageOffset, parsePage } from "./queryParams";
import { runStatsText, runStatusLabel } from "./sources";
import { isTaskFailed, isTaskFinished, pollInterval } from "./tasks";

describe("parseList", () => {
  it("строки и запятые, без пустых и повторов", () => {
    expect(parseList("Python, backend\n\n  python \nFastAPI,")).toEqual([
      "Python",
      "backend",
      "FastAPI",
    ]);
  });

  it("formatList — по строке на значение", () => {
    expect(parseList(formatList(["a", "b"]))).toEqual(["a", "b"]);
  });
});

describe("tasks", () => {
  const task = (state: string) => ({ task_id: "1", state, result: null, error: null });

  it("завершённые состояния", () => {
    expect(isTaskFinished(task("SUCCESS"))).toBe(true);
    expect(isTaskFinished(task("FAILURE"))).toBe(true);
    expect(isTaskFinished(task("PENDING"))).toBe(false);
    expect(isTaskFinished(undefined)).toBe(false);
    expect(isTaskFailed(task("FAILURE"))).toBe(true);
    expect(isTaskFailed(task("SUCCESS"))).toBe(false);
  });

  it("интервал опроса растёт до 10 секунд", () => {
    expect([0, 1, 2, 3, 4, 10].map(pollInterval)).toEqual([1000, 2000, 4000, 8000, 10000, 10000]);
  });
});

describe("sources", () => {
  it("итог сбора словами", () => {
    expect(
      runStatsText({ received: 910, changed: 0, deactivated: 2, details_queued: 1, deactivation_skipped: false }),
    ).toBe("получено 910, изменилось 0, снято 2, описаний в очереди 1");
    expect(runStatsText({ received: 100, deactivation_skipped: true })).toBe(
      "получено 100, снятие пропущено: обход неполный",
    );
    expect(runStatsText(null)).toBeNull();
  });

  it("статус сбора", () => {
    expect(runStatusLabel(null)).toBe("ещё не запускался");
    expect(runStatusLabel("success")).toBe("успешно");
    expect(runStatusLabel("new_status")).toBe("new_status");
  });
});

describe("labels", () => {
  it("известные значения переводятся, новые — как есть", () => {
    expect(contractLabel("GPH")).toBe("ГПХ");
    expect(contractLabel("CONTRACT")).toBe("CONTRACT");
    expect(workFormatLabel("remote")).toBe("удалённо");
    expect(workFormatLabel("moon")).toBe("moon");
  });
});

describe("queryParams", () => {
  it("значение из списка или null", () => {
    expect(oneOf("b", ["a", "b"])).toBe("b");
    expect(oneOf("c", ["a", "b"])).toBeNull();
    expect(oneOf(null, ["a"])).toBeNull();
  });

  it("целое в диапазоне, без дробей и знаков", () => {
    expect(intInRange("5", 1, 10)).toBe(5);
    expect(intInRange("1.5", 1, 10)).toBeNull();
    expect(intInRange("-1", 0, 10)).toBeNull();
    expect(intInRange("11", 1, 10)).toBeNull();
  });

  it("страница и смещение", () => {
    expect(parsePage("3")).toBe(3);
    expect(parsePage("0")).toBe(1);
    expect(parsePage("abc")).toBe(1);
    expect(pageOffset(3)).toBe(40);
  });
});

describe("optionsFrom", () => {
  it("варианты с пунктом «без фильтра» и без него", () => {
    const labels = { a: "А", b: "Б" };
    expect(optionsFrom(["a", "b"], labels)).toEqual([
      { value: "a", label: "А" },
      { value: "b", label: "Б" },
    ]);
    expect(optionsFrom(["a"], labels, "Любой")[0]).toEqual({ value: "", label: "Любой" });
  });
});
