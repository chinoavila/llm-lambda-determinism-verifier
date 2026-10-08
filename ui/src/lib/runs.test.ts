import { describe, expect, it } from "vitest";
import type { Rule } from "../api";
import { blankRule } from "./rules";
import { runSelection, unreviewedRules, type RunForm } from "./runs";

const form: RunForm = { source: "corpus", picked: [], repetitions: 5, model: "m", temperature: 0, resume: null };

describe("runSelection", () => {
  it("manda modelo y temperatura siempre, case_ids y resume solo cuando corresponden", () => {
    expect(runSelection(form)).toEqual({ source: "corpus", repetitions: 5, model: "m", temperature: 0 });
    expect(runSelection({ ...form, picked: ["a"], resume: "r1" })).toMatchObject({ case_ids: ["a"], resume: "r1" });
    expect(runSelection({ ...form, source: "fixtures", picked: ["a"] })).not.toHaveProperty("case_ids");
  });
});

describe("unreviewedRules", () => {
  const rule = (case_id: string, status?: "aprobada" | "cambios"): Rule => ({
    ...blankRule(),
    case_id,
    ...(status ? { review: { status, comments: [] } } : {}),
  });
  const rules = [rule("a", "aprobada"), rule("b"), rule("c", "cambios")];

  it("lista las reglas elegidas sin review aprobada", () => {
    expect(unreviewedRules(rules, form)).toEqual(["b", "c"]);
    expect(unreviewedRules(rules, { ...form, picked: ["a", "c"] })).toEqual(["c"]);
    expect(unreviewedRules(rules, { ...form, source: "fixtures" })).toEqual([]);
  });
});
