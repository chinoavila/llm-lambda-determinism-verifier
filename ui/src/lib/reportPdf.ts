// Definición del PDF del reporte con IA (specs/ui.md §Reporte con IA). Función pura: el
// texto viene del LLM y las tablas de los anexos salen de la evidencia, nunca del texto.
// pdfmake se carga recién al descargar (`downloadReportPdf`), para no agrandar el bundle.
import type { Content, TableCell } from "pdfmake";
import type { TDocumentDefinitions, TVirtualFileSystem } from "pdfmake/interfaces";
import type { AiReport, Group, ObservationStatus, Outcome } from "../api";
import { GROUP, OUTCOME } from "../pages/RecordsPage";
import type { Evidence, ReportData } from "./report";
import { fmtRate, GROUPS, LAYERS, OUTCOMES, type BreakdownRow, type CountRow, type PassCount } from "./stats";

/** Títulos de las observaciones de report_methodology.md §4, en el mismo orden. */
export const OBSERVATION_TITLES = [
  "El proveedor intercepta fallas estructurales (modo JSON)",
  "El formato de transporte perjudica a los baselines",
  "El preámbulo del Baseline 2 introduce fallas propias",
  "Modelos no balanceados entre categorías",
  "La categoría 2 casi no provoca errores de tipos",
  "Los bloqueos del motor son mayormente de estructura",
  "Una repetición no alcanza para medir variabilidad",
  "Consistencia de los resultados esperados",
];

export const STATUS_LABEL: Record<ObservationStatus, string> = {
  se_repite: "Se repite",
  no_se_repite: "No se repite",
  no_concluyente: "No concluyente",
};

/** Referencias fijas de report_methodology.md §6: el LLM no agrega otras. */
export const REFERENCES = [
  "Cherednichenko, O., Maliarenko, V.: The dispatcher: bridging the probabilistic gap in automated decision modeling (2025). https://pm.khpi.edu.ua/article/view/350034",
  "Mündler, N., He, J., Wang, H., Sen, K., Song, D., Vechev, M.: Type-Constrained Code Generation with Language Models (2025). https://dl.acm.org/doi/10.1145/3729274",
  "Zhang, Y., Pientka, B., Si, X.: Evaluating LLMs in the context of a functional programming course: a comprehensive study (2026). https://programming-journal.org/2026/11/5",
];

export type ReportMeta = { model: string; createdAt: string };

const head = (cells: string[]): TableCell[] => cells.map((text) => ({ text, style: "th" }));
const num = (n: number | string): TableCell => ({ text: String(n), alignment: "right" });
const passCell = (p: PassCount): TableCell => ({
  text: p.pass + p.fail ? `${fmtRate(p.rate)} (${p.pass}/${p.pass + p.fail})` : "—",
  alignment: "right",
});
const ms = (v: number | null) => (v === null ? "—" : `${Math.round(v).toLocaleString("es-AR")} ms`);
const value = (r: { type: string; value: unknown } | null) => (r ? `${r.type} ${JSON.stringify(r.value)}` : "—");

function table(widths: (string | number)[], header: string[], body: TableCell[][]): Content {
  return {
    table: { headerRows: 1, widths, body: [head(header), ...body], dontBreakRows: true },
    layout: "lightHorizontalLines",
    margin: [0, 4, 0, 12],
  };
}

const h1 = (text: string, pageBreak = false): Content => ({ text, style: "h1", ...(pageBreak ? { pageBreak: "before" as const } : {}) });
const h2 = (text: string): Content => ({ text, style: "h2" });
const note = (text: string): Content => ({ text, style: "note" });

function breakdown(first: string, rows: BreakdownRow[]): Content {
  return table(
    ["*", ...GROUPS.map(() => "auto")],
    [first, ...GROUPS.map((g) => GROUP[g]!)],
    rows.map((r) => [r.label, ...GROUPS.map((g) => passCell(r.byGroup[g]))]),
  );
}

function counts(first: string, rows: CountRow[]): Content {
  if (!rows.length) return note("Sin renglones.");
  return table(
    ["*", ...GROUPS.map(() => "auto"), "auto"],
    [first, ...GROUPS.map((g) => GROUP[g]!), "Total"],
    rows.map((r) => [{ text: r.key, style: "mono" }, ...GROUPS.map((g) => num(r.byGroup[g])), num(r.total)]),
  );
}

function perGroupRow(label: string, values: Record<Group, number>): TableCell[] {
  return [label, ...GROUPS.map((g) => num(values[g]))];
}

/** Anexo A: las mismas cifras que la pantalla de Estadísticas, más los indicadores de §4. */
export function evidenceAnnex(e: Evidence, passByRule: BreakdownRow[]): Content[] {
  const o = e.observations;
  const categories = [...new Set(Object.values(e.generations_by_model_and_category).flatMap((c) => Object.keys(c)))].sort();
  return [
    h1("Anexo A. Evidencia de la corrida", true),
    note(`Cifras calculadas por la SPA a partir de out/${e.run.run_id}.jsonl, con las mismas funciones que la pantalla de Estadísticas. pass@1 = ${e.definitions.pass_at_1}; ${e.definitions.renglones}.`),
    h2("A.1 pass@1 por grupo"),
    table(["*", "auto", "auto", "auto"], ["Grupo", "pass@1", "Pasan / con expected", "Sin expected"], GROUPS.map((g) => {
      const p = e.pass_by_group[g];
      return [GROUP[g]!, num(fmtRate(p.rate)), num(`${p.pass} / ${p.pass + p.fail}`), num(p.noExpected)];
    })),
    h2("A.2 Desenlaces por grupo (renglones)"),
    table(["*", ...OUTCOMES.map(() => "auto")], ["Grupo", ...OUTCOMES.map((x: Outcome) => OUTCOME[x].label)], GROUPS.map((g) => [GROUP[g]!, ...OUTCOMES.map((x) => num(e.outcomes_by_group[g][x]))])),
    h2("A.3 Bloqueos por etapa (renglones)"),
    counts("Etapa", e.blocked_stages),
    h2("A.4 pass@1 por categoría"),
    breakdown("Categoría", e.pass_by_category),
    h2("A.5 pass@1 por dominio"),
    breakdown("Dominio", e.pass_by_domain),
    h2("A.6 pass@1 por modelo"),
    breakdown("Modelo", e.pass_by_model),
    h2("A.7 Generaciones del Tratamiento por modelo y categoría"),
    table(["*", ...categories.map(() => "auto")], ["Modelo", ...categories], Object.entries(e.generations_by_model_and_category).map(([m, c]) => [{ text: m, style: "mono" }, ...categories.map((k) => num(c[k] ?? 0))])),
    h2("A.8 Códigos de error (renglones)"),
    counts("Código", e.errors),
    h2("A.9 Duración (duration_ms por renglón)"),
    table(["*", "auto", "auto", "auto"], ["Grupo", "n", "Media", "Mediana"], GROUPS.map((g) => {
      const d = e.duration[g];
      return [GROUP[g]!, num(d.n), num(ms(d.mean)), num(ms(d.median))];
    })),
    h2("A.10 Indicadores de las observaciones metodológicas (generaciones, salvo indicación)"),
    table(["*", ...GROUPS.map(() => "auto")], ["Indicador", ...GROUPS.map((g) => GROUP[g]!)], [
      perGroupRow("1. Generaciones con error del LLM", o.llm_error_generations),
      ["2. SyntaxError con saltos de línea escapados dos veces", "—", num(o.double_escaped_syntax_errors.baseline1), num(o.double_escaped_syntax_errors.baseline2)],
      ["3. Baseline 2: Data redefinido o __future__", "—", "—", num(o.baseline2_harness_failures.redefined_or_future_import)],
      ["3. Baseline 2: firma distinta de la exigida", "—", "—", num(o.baseline2_harness_failures.signature_mismatch)],
      [`5. Cat. 2: bloqueos por alcance o tipos (de ${o.category2.treatment_generations})`, num(o.category2.treatment_scope_or_type_blocks), "—", "—"],
      perGroupRow("5. Renglones con el valor correcto y otro tipo", o.category2.result_type_mismatch_rows),
    ]),
    table(["*", "auto"], ["6. Bloqueos del Tratamiento por código", "Generaciones"], Object.entries(o.treatment_blocks_by_code).sort(([, a], [, b]) => b - a).map(([k, n]) => [{ text: k, style: "mono" }, num(n)])),
    note(`7. Repeticiones: ${e.run.repetitions}. Temperatura: ${e.run.temperature}.`),
    ...(e.pass_at_k.length > 1
      ? [
          table(["*", ...GROUPS.map(() => "auto")], ["7. pass@k (reglas con k generaciones)", ...GROUPS.map((g) => GROUP[g]!)], [
            ...e.pass_at_k.map((r) => [`pass@${r.k}`, ...GROUPS.map((g) => num(`${fmtRate(r.byGroup[g].rate)} (${r.byGroup[g].cases})`))]),
            ["7. Reglas inestables entre repeticiones", ...GROUPS.map((g) => num(e.consistency[g].cases ? `${e.consistency[g].unstable} de ${e.consistency[g].cases}` : "—"))],
          ]),
        ]
      : []),
    note(`8. Escenarios en que los tres grupos coinciden entre sí y contradicen el expected: ${o.expected_contradictions.scenarios}.`),
    h2("A.11 Dónde se detecta cada falla (generaciones con expected)"),
    note("Bloqueada: el motor en el Tratamiento, el análisis previo en los baselines. Resultado incorrecto: ejecutó y solo lo detectaron los escenarios (los errores lógicos de la categoría 3)."),
    table(["*", "auto", ...LAYERS.map(() => "auto"), "auto"], ["Categoría", "Grupo", "LLM", "Bloqueada", "Error ejec.", "Incorrecto", "Acierta", "Total"], e.failure_layers_by_category.map((r) => [r.label, GROUP[r.group]!, ...LAYERS.map((l) => num(r.counts[l])), num(r.total)])),
    h2("A.12 pass@1 por regla"),
    breakdown("Regla", passByRule),
  ];
}

/** Anexo B: la muestra de fallos que recibió el LLM. */
export function failureAnnex(e: Evidence): Content[] {
  return [
    h1("Anexo B. Muestra de generaciones que fallan", true),
    note("Hasta tres por grupo, repartidas entre categorías. Es la misma muestra que recibió el LLM; llm_raw está truncado."),
    ...e.failure_sample.flatMap((f): Content[] => [
      h2(`${f.case_id} · ${GROUP[f.group]} · ${f.category}`),
      {
        text: [
          { text: "Modelo: ", bold: true }, `${f.model}   `,
          { text: "Desenlace: ", bold: true }, `${f.outcome} (${f.stage})   `,
          { text: "Error: ", bold: true }, `${f.error_code ?? "—"}\n`,
          { text: "Resultado: ", bold: true }, `${value(f.result)}   `,
          { text: "Esperado: ", bold: true }, value(f.expected),
        ],
        margin: [0, 0, 0, 4],
      },
      ...(f.error_message ? [note(f.error_message)] : []),
      { text: f.llm_raw ?? "(sin respuesta)", style: "code" },
    ]),
  ];
}

export function reportDocDefinition(report: AiReport, data: ReportData, meta: ReportMeta): TDocumentDefinitions {
  const e = data.evidence;
  const observations = [...report.observations].sort((a, b) => a.number - b.number);
  return {
    pageSize: "A4",
    pageMargins: [56, 56, 56, 56],
    info: { title: report.title, subject: `Corrida ${e.run.run_id}`, creator: "Mesa del pipeline", producer: `Texto redactado por ${meta.model}` },
    defaultStyle: { font: "Roboto", fontSize: 10, lineHeight: 1.25 },
    styles: {
      title: { fontSize: 18, bold: true, margin: [0, 0, 0, 6] },
      subtitle: { fontSize: 11, color: "#555555", margin: [0, 0, 0, 16] },
      h1: { fontSize: 13, bold: true, margin: [0, 14, 0, 6] },
      h2: { fontSize: 11, bold: true, margin: [0, 10, 0, 4] },
      p: { alignment: "justify", margin: [0, 0, 0, 6] },
      th: { bold: true, fontSize: 9 },
      note: { fontSize: 8.5, color: "#555555", margin: [0, 0, 0, 6] },
      mono: { fontSize: 8.5 },
      code: { fontSize: 7.5, color: "#333333", background: "#f2f2f2", margin: [0, 0, 0, 10] },
    },
    footer: (page: number, pages: number) => ({ text: `${e.run.run_id} · ${page} / ${pages}`, alignment: "center", fontSize: 8, color: "#777777", margin: [0, 20, 0, 0] }),
    content: [
      { text: report.title, style: "title" },
      { text: `Reporte de la corrida ${e.run.run_id}`, style: "subtitle" },
      table(["auto", "*"], ["Dato", "Valor"], [
        ["Corrida", { text: e.run.run_id, style: "mono" }],
        ["Última escritura", e.run.modified],
        ["Renglones / generaciones", `${e.run.records} / ${e.run.generations}`],
        ["Reglas / escenarios", `${e.run.cases} / ${e.run.scenarios}`],
        ["Repeticiones", String(e.run.repetitions)],
        ["Modelos de la corrida", e.run.models.join(", ")],
        ["Temperatura", e.run.temperature],
        ["Tokens", e.run.tokens.per_call === null ? "no registrados" : `${e.run.tokens.total} (${Math.round(e.run.tokens.per_call)} por llamada)`],
        ["Texto redactado por", `${meta.model}, ${meta.createdAt}`],
      ]),
      note(`El texto de este informe lo redactó ${meta.model} a partir de la evidencia del Anexo A y de las bases metodológicas del proyecto (pipeline/pipeline/report_methodology.md). Las cifras de las tablas las calculó la SPA a partir de out/${e.run.run_id}.jsonl; ante una diferencia con el texto, valen las tablas.`),
      h1("Resumen"),
      { text: report.abstract, style: "p" },
      ...report.sections.flatMap((s): Content[] => [h1(s.heading), ...s.paragraphs.map((p): Content => ({ text: p, style: "p" }))]),
      h1("Contraste con las observaciones metodológicas"),
      table(["auto", 120, "auto", "*"], ["N.º", "Observación", "Estado", "Comentario"], observations.map((o) => [num(o.number), OBSERVATION_TITLES[o.number - 1] ?? "", STATUS_LABEL[o.status], o.text])),
      h1("Limitaciones"),
      { ul: report.limitations, margin: [0, 0, 0, 6] },
      h1("Conclusiones"),
      { ul: report.conclusions, margin: [0, 0, 0, 6] },
      h1("Referencias"),
      { ol: REFERENCES, fontSize: 9 },
      ...evidenceAnnex(e, data.passByRule),
      ...failureAnnex(e),
    ],
  };
}

/** Carga pdfmake con sus fuentes embebidas (funciona sin internet) y descarga el PDF. */
export async function downloadReportPdf(doc: TDocumentDefinitions, fileName: string): Promise<void> {
  const [pdfModule, vfsModule] = await Promise.all([import("pdfmake/build/pdfmake"), import("pdfmake/build/vfs_fonts")]);
  const pdfMake = (pdfModule as unknown as { default?: typeof pdfModule }).default ?? pdfModule;
  const vfs = ((vfsModule as { default?: unknown }).default ?? vfsModule) as TVirtualFileSystem;
  pdfMake.addVirtualFileSystem(vfs);
  await pdfMake.createPdf(doc).download(fileName);
}
