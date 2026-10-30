import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

export type PageSize = 25 | 50 | 100 | "all";

export type Pagination<T> = {
  items: T[];
  page: number;
  pageCount: number;
  pageSize: PageSize;
  total: number;
  start: number;
  end: number;
  setPage: (page: number) => void;
  setPageSize: (size: PageSize) => void;
};

/** Client-side paging shared by every data table in the UI. */
export function usePagination<T>(items: T[], resetKey?: string): Pagination<T> {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(25);

  useEffect(() => {
    setPage(1);
  }, [items.length, resetKey]);

  const pageCount = pageSize === "all" ? 1 : Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const visibleItems = useMemo(() => {
    if (pageSize === "all") return items;
    const start = (currentPage - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [currentPage, items, pageSize]);

  return {
    items: visibleItems,
    page: currentPage,
    pageCount,
    pageSize,
    total: items.length,
    start: items.length === 0 ? 0 : (currentPage - 1) * (pageSize === "all" ? items.length : pageSize) + 1,
    end: pageSize === "all" ? items.length : Math.min(currentPage * pageSize, items.length),
    setPage: (next) => setPage(Math.max(1, Math.min(next, pageCount))),
    setPageSize: (size) => {
      setPageSize(size);
      setPage(1);
    },
  };
}

export function TablePagination<T>({
  pagination,
  label,
}: {
  pagination: Pagination<T>;
  label: string;
}): ReactNode {
  const { page, pageCount, pageSize, total, start, end, setPage, setPageSize } = pagination;
  return (
    <nav aria-label={`Paginación: ${label}`} className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-[12.5px]">
      <span className="text-muted" aria-live="polite">
        {total === 0 ? "Sin resultados" : `Mostrando ${start}–${end} de ${total}`}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-muted">
          Filas por página
          <select
            aria-label={`Filas por página: ${label}`}
            value={pageSize}
            onChange={(event) => {
              const value = event.target.value;
              if (value === "all") setPageSize("all");
              else if (value === "25") setPageSize(25);
              else if (value === "50") setPageSize(50);
              else if (value === "100") setPageSize(100);
            }}
            className="rounded-md border border-line bg-surface px-2 py-1 text-ink"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value="all">Todos</option>
          </select>
        </label>
        <button
          type="button"
          aria-label={`Página anterior: ${label}`}
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
          className="rounded-md border border-line bg-surface px-2.5 py-1 disabled:opacity-50"
        >
          Anterior
        </button>
        <span className="tabular-nums text-muted">
          Página {page} de {pageCount}
        </span>
        <button
          type="button"
          aria-label={`Página siguiente: ${label}`}
          disabled={page >= pageCount}
          onClick={() => setPage(page + 1)}
          className="rounded-md border border-line bg-surface px-2.5 py-1 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>
    </nav>
  );
}
