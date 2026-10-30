import { describe, expect, it } from "vitest";
import type { RecordRow } from "../api";
import { crc32, toCsv, toJsonl, toMarkdown, toPdf, toTxt, toXlsx } from "./export";

const row = (over: Partial<RecordRow> = {}): RecordRow => ({
  run_id: "r1",
  case_id: "credito_01",
  group: "treatment",
  repetition: 1,
  scenario_id: "s1",
  model: "m",
  timestamp: "2026-10-07T12:00:00Z",
  llm_raw: '{"expr": 1}',
  outcome: "executed",
  stage: "execution",
  result: { type: "Decimal", value: "0.30" },
  error: null,
  duration_ms: 12,
  expected: { type: "Decimal", value: "0.3" },
  ...over,
});

const latin1 = (b: Uint8Array) => Array.from(b, (c) => String.fromCharCode(c)).join("");

describe("toJsonl", () => {
  it("devuelve los registros como en out/, sin el expected que agrega la API", () => {
    const lines = toJsonl([row(), row({ scenario_id: "s2" })]).trimEnd().split("\n");
    expect(lines).toHaveLength(2);
    const first = JSON.parse(lines[0]!);
    expect(first).not.toHaveProperty("expected");
    expect(first.result).toEqual({ type: "Decimal", value: "0.30" });
  });
});

describe("toCsv", () => {
  it("cita los campos con comas, comillas o saltos de línea", () => {
    const csv = toCsv([row({ llm_raw: 'a, "b"\nc' })]);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    expect(csv.slice(1).startsWith("run_id,case_id,")).toBe(true);
    expect(csv).toContain(',0.3,'); // expected_value
    expect(csv).toContain('"a, ""b""\nc"\r\n');
  });
});

describe("toTxt y toMarkdown", () => {
  it("incluyen la respuesta cruda y el expected de cada registro", () => {
    const txt = toTxt("r1", [row()]);
    expect(txt).toContain("credito_01 · treatment · rep 1 · s1");
    expect(txt).toMatch(/expected_value\s+0\.3/);
    expect(txt).toContain('{"expr": 1}');
  });

  it("usa una cerca más larga que cualquier racha de backticks de llm_raw", () => {
    const md = toMarkdown("r1", [row({ llm_raw: "```python\nx = 1\n```" })]);
    expect(md).toContain("````\n```python\nx = 1\n```\n````");
    expect(toMarkdown("r1", [row({ llm_raw: null })])).toContain("_sin respuesta_");
  });
});

describe("toXlsx", () => {
  it("calcula el CRC-32 estándar", () => {
    expect(crc32(new TextEncoder().encode("123456789"))).toBe(0xcbf43926);
  });

  it("arma un ZIP con las partes del libro y escapa el XML", () => {
    const bytes = toXlsx([row({ llm_raw: "<a & b>\u0001" })]);
    const s = new TextDecoder().decode(bytes);
    expect(s.startsWith("PK\u0003\u0004")).toBe(true);
    for (const part of ["[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml", "xl/styles.xml"]) expect(s).toContain(part);
    expect(s).toContain("&lt;a &amp; b&gt;</t>");
    expect(s).toContain('<c r="P2"><v>12</v></c>'); // duration_ms numérico
    const end = new DataView(bytes.buffer, bytes.length - 22);
    expect(end.getUint32(0, true)).toBe(0x06054b50);
    expect(end.getUint16(10, true)).toBe(6);
  });
});

describe("toPdf", () => {
  it("apunta cada entrada del xref al comienzo de su objeto", () => {
    const pdf = latin1(toPdf("r1", Array.from({ length: 10 }, (_, i) => row({ scenario_id: `s${i}`, llm_raw: "(año) \\ — ✓" }))));
    expect(pdf.startsWith("%PDF-1.4")).toBe(true);
    const xref = Number(/startxref\n(\d+)/.exec(pdf)![1]);
    expect(pdf.slice(xref, xref + 4)).toBe("xref");
    const offsets = [...pdf.slice(xref).matchAll(/^(\d{10}) 00000 n $/gm)].map((m) => Number(m[1]));
    offsets.forEach((o, i) => expect(pdf.slice(o, o + `${i + 1} 0 obj`.length)).toBe(`${i + 1} 0 obj`));
    expect(Number(/\/Count (\d+)/.exec(pdf)![1])).toBeGreaterThan(1);
    expect(pdf).toContain("(\\(año\\) \\\\ \x97 ?) Tj");
  });
});
