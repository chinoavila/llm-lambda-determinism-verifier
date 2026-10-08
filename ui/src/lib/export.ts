// Exportación de los registros de una corrida a archivos. Solo transforma renglones:
// sin conteos, tasas ni resúmenes (specs/mission.md §2, specs/ui.md). Sin dependencias:
// el XLSX es un ZIP sin comprimir y el PDF usa la fuente Courier estándar.
import type { RecordRow, Result } from "../api";

export type ExportFormat = "jsonl" | "txt" | "md" | "csv" | "xlsx" | "pdf";

export const EXPORT_FORMATS: { format: ExportFormat; label: string; mime: string }[] = [
  { format: "jsonl", label: "JSONL", mime: "application/x-ndjson" },
  { format: "txt", label: "TXT", mime: "text/plain;charset=utf-8" },
  { format: "md", label: "MD", mime: "text/markdown;charset=utf-8" },
  { format: "csv", label: "CSV", mime: "text/csv;charset=utf-8" },
  { format: "xlsx", label: "Excel", mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  { format: "pdf", label: "PDF", mime: "application/pdf" },
];

type Cell = string | number | null;

// Columnas de las vistas tabulares: el registro plano más el `expected` de su escenario.
const COLUMNS: [string, (r: RecordRow) => Cell][] = [
  ["run_id", (r) => r.run_id],
  ["case_id", (r) => r.case_id],
  ["group", (r) => r.group],
  ["repetition", (r) => r.repetition],
  ["scenario_id", (r) => r.scenario_id],
  ["model", (r) => r.model],
  ["timestamp", (r) => r.timestamp],
  ["outcome", (r) => r.outcome],
  ["stage", (r) => r.stage],
  ["result_type", (r) => r.result?.type ?? null],
  ["result_value", (r) => value(r.result)],
  ["expected_type", (r) => r.expected?.type ?? null],
  ["expected_value", (r) => value(r.expected)],
  ["error_code", (r) => r.error?.code ?? null],
  ["error_message", (r) => r.error?.message ?? null],
  ["duration_ms", (r) => r.duration_ms],
  ["llm_raw", (r) => r.llm_raw],
];

function value(r: Result | null | undefined): Cell {
  if (!r) return null;
  return typeof r.value === "string" || typeof r.value === "number" ? r.value : JSON.stringify(r.value);
}

const text = (c: Cell) => (c === null ? "" : String(c));

/** Los registros tal como están en out/<run_id>.jsonl (sin el `expected` que agrega la API). */
export function toJsonl(rows: RecordRow[]): string {
  return rows.map(({ expected: _expected, ...record }) => JSON.stringify(record)).join("\n") + (rows.length ? "\n" : "");
}

const BOM = String.fromCharCode(0xfeff);

/** RFC 4180, con BOM para que Excel lo abra como UTF-8. */
export function toCsv(rows: RecordRow[]): string {
  const quote = (c: Cell) => {
    const s = text(c);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [COLUMNS.map(([h]) => h), ...rows.map((r) => COLUMNS.map(([, get]) => quote(get(r))))];
  return BOM + lines.map((l) => l.join(",")).join("\r\n") + "\r\n";
}

const title = (r: RecordRow) => `${r.case_id} · ${r.group} · rep ${r.repetition} · ${r.scenario_id}`;

export function toTxt(runId: string, rows: RecordRow[]): string {
  const width = Math.max(...COLUMNS.map(([h]) => h.length));
  const blocks = rows.map((r) => {
    const fields = COLUMNS.filter(([h]) => h !== "llm_raw").map(([h, get]) => `${h.padEnd(width)}  ${text(get(r)) || "—"}`);
    return [title(r), "-".repeat(title(r).length), ...fields, "", "llm_raw:", r.llm_raw ?? "—"].join("\n");
  });
  return [`Corrida ${runId}`, "=".repeat(`Corrida ${runId}`.length), "", blocks.join("\n\n" + "=".repeat(60) + "\n\n")].join("\n") + "\n";
}

export function toMarkdown(runId: string, rows: RecordRow[]): string {
  const inline = (c: Cell) => (text(c) ? `\`${text(c).replace(/`/g, "'")}\`` : "—");
  const fence = (s: string) => "`".repeat(Math.max(3, ...[...s.matchAll(/`+/g)].map((m) => m[0].length + 1)));
  const sections = rows.map((r) => {
    const fields = COLUMNS.filter(([h]) => h !== "llm_raw").map(([h, get]) => `- **${h}:** ${inline(get(r))}`);
    const raw = r.llm_raw === null ? "_sin respuesta_" : `${fence(r.llm_raw)}\n${r.llm_raw}\n${fence(r.llm_raw)}`;
    return [`## ${title(r)}`, "", ...fields, "", "**llm_raw:**", "", raw].join("\n");
  });
  return [`# Corrida \`${runId}\``, "", ...sections.flatMap((s) => [s, ""])].join("\n");
}

// --- XLSX -------------------------------------------------------------------

// Caracteres que XML 1.0 no admite: controles y sustitutos sueltos.
const XML_INVALID = /[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFE\uFFFF]|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g;
const xml = (s: string) =>
  s.replace(XML_INVALID, "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const columnName = (i: number): string => (i < 26 ? "" : columnName(Math.floor(i / 26) - 1)) + String.fromCharCode(65 + (i % 26));

const XLSX_CELL_MAX = 32767;

export function toXlsx(rows: RecordRow[]): Uint8Array<ArrayBuffer> {
  const cell = (c: Cell, col: number, row: number, style = 0) => {
    const ref = `${columnName(col)}${row}`;
    const s = style ? ` s="${style}"` : "";
    if (c === null) return "";
    if (typeof c === "number") return `<c r="${ref}"${s}><v>${c}</v></c>`;
    return `<c r="${ref}"${s} t="inlineStr"><is><t xml:space="preserve">${xml(c.slice(0, XLSX_CELL_MAX))}</t></is></c>`;
  };
  const header = `<row r="1">${COLUMNS.map(([h], i) => cell(h, i, 1, 1)).join("")}</row>`;
  const body = rows.map((r, j) => `<row r="${j + 2}">${COLUMNS.map(([, get], i) => cell(get(r), i, j + 2)).join("")}</row>`).join("");
  const ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';
  const rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
  const decl = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';
  return zip([
    [
      "[Content_Types].xml",
      decl +
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
        '<Default Extension="xml" ContentType="application/xml"/>' +
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
        "</Types>",
    ],
    [
      "_rels/.rels",
      decl +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        `<Relationship Id="rId1" Type="${rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
    ],
    [
      "xl/workbook.xml",
      decl + `<workbook ${ns} xmlns:r="${rel}"><sheets><sheet name="registros" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    ],
    [
      "xl/_rels/workbook.xml.rels",
      decl +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        `<Relationship Id="rId1" Type="${rel}/worksheet" Target="worksheets/sheet1.xml"/>` +
        `<Relationship Id="rId2" Type="${rel}/styles" Target="styles.xml"/></Relationships>`,
    ],
    [
      "xl/styles.xml",
      decl +
        `<styleSheet ${ns}>` +
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>' +
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>' +
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>' +
        "</styleSheet>",
    ],
    [
      "xl/worksheets/sheet1.xml",
      decl +
        `<worksheet ${ns}>` +
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>' +
        `<sheetData>${header}${body}</sheetData></worksheet>`,
    ],
  ]);
}

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

export function crc32(data: Uint8Array): number {
  let c = 0xffffffff;
  for (const b of data) c = CRC_TABLE[(c ^ b) & 0xff]! ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** ZIP con los archivos guardados sin comprimir (método 0). */
export function zip(files: [string, string][]): Uint8Array<ArrayBuffer> {
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const [name, content] of files) {
    const n = enc.encode(name);
    const data = enc.encode(content);
    const crc = crc32(data);
    const local = new Uint8Array(30 + n.length);
    const lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, data.length, true);
    lv.setUint32(22, data.length, true);
    lv.setUint16(26, n.length, true);
    local.set(n, 30);
    const dir = new Uint8Array(46 + n.length);
    const dv = new DataView(dir.buffer);
    dv.setUint32(0, 0x02014b50, true);
    dv.setUint16(4, 20, true);
    dv.setUint16(6, 20, true);
    dv.setUint32(16, crc, true);
    dv.setUint32(20, data.length, true);
    dv.setUint32(24, data.length, true);
    dv.setUint16(28, n.length, true);
    dv.setUint32(42, offset, true);
    dir.set(n, 46);
    parts.push(local, data);
    central.push(dir);
    offset += local.length + data.length;
  }
  const size = central.reduce((s, d) => s + d.length, 0);
  const end = new Uint8Array(22);
  const ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, files.length, true);
  ev.setUint16(10, files.length, true);
  ev.setUint32(12, size, true);
  ev.setUint32(16, offset, true);
  return concat([...parts, ...central, end]);
}

function concat(chunks: Uint8Array[]): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(chunks.reduce((s, c) => s + c.length, 0));
  let at = 0;
  for (const c of chunks) {
    out.set(c, at);
    at += c.length;
  }
  return out;
}

// --- PDF --------------------------------------------------------------------

// Caracteres de WinAnsiEncoding fuera de Latin-1 que aparecen seguido en texto.
const WIN_ANSI: Record<string, number> = { "€": 0x80, "‘": 0x91, "’": 0x92, "“": 0x93, "”": 0x94, "•": 0x95, "–": 0x96, "—": 0x97, "…": 0x85 };

const PAGE = { width: 842, height: 595, margin: 36, size: 8, leading: 10 }; // A4 apaisada
const PDF_COLUMNS = Math.floor((PAGE.width - 2 * PAGE.margin) / (PAGE.size * 0.6));
const PDF_LINES = Math.floor((PAGE.height - 2 * PAGE.margin) / PAGE.leading);

/** El mismo contenido que el TXT, en Courier sobre páginas A4 apaisadas. */
export function toPdf(runId: string, rows: RecordRow[]): Uint8Array<ArrayBuffer> {
  const lines = toTxt(runId, rows)
    .replace(/\t/g, "  ")
    .split(/\r?\n/)
    .flatMap((l) => (l.length <= PDF_COLUMNS ? [l] : Array.from({ length: Math.ceil(l.length / PDF_COLUMNS) }, (_, i) => l.slice(i * PDF_COLUMNS, (i + 1) * PDF_COLUMNS))));
  const pages: string[][] = [];
  for (let i = 0; i < lines.length; i += PDF_LINES) pages.push(lines.slice(i, i + PDF_LINES));

  const escape = (s: string) => s.replace(/[\\()]/g, (c) => `\\${c}`);
  const objects: string[] = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    `<< /Type /Pages /Count ${pages.length} /Kids [${pages.map((_, i) => `${4 + 2 * i} 0 R`).join(" ")}] >>`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
  ];
  pages.forEach((page, i) => {
    const top = PAGE.height - PAGE.margin - PAGE.size;
    const stream = `BT /F1 ${PAGE.size} Tf ${PAGE.leading} TL ${PAGE.margin} ${top} Td\n${page.map((l) => `(${escape(l)}) Tj T*`).join("\n")}\nET`;
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE.width} ${PAGE.height}] /Resources << /Font << /F1 3 0 R >> >> /Contents ${5 + 2 * i} 0 R >>`,
      `<< /Length ${winAnsi(stream).length} >>\nstream\n${stream}\nendstream`,
    );
  });

  let out = "%PDF-1.4\n";
  const offsets = objects.map((body, i) => {
    const at = winAnsi(out).length;
    out += `${i + 1} 0 obj\n${body}\nendobj\n`;
    return at;
  });
  const xref = winAnsi(out).length;
  out +=
    `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n` +
    offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("") +
    `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return winAnsi(out);
}

/** Un byte por carácter: Latin-1 y los de WIN_ANSI; el resto, "?". */
function winAnsi(s: string): Uint8Array<ArrayBuffer> {
  const chars = [...s];
  const out = new Uint8Array(chars.length);
  chars.forEach((c, i) => {
    const code = c.codePointAt(0)!;
    out[i] = WIN_ANSI[c] ?? (code < 0x80 || (code >= 0xa0 && code <= 0xff) ? code : 0x3f);
  });
  return out;
}

export function exportRecords(runId: string, rows: RecordRow[], format: ExportFormat): string | Uint8Array<ArrayBuffer> {
  switch (format) {
    case "jsonl":
      return toJsonl(rows);
    case "txt":
      return toTxt(runId, rows);
    case "md":
      return toMarkdown(runId, rows);
    case "csv":
      return toCsv(rows);
    case "xlsx":
      return toXlsx(rows);
    case "pdf":
      return toPdf(runId, rows);
  }
}
