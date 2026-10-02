import { useSyncExternalStore } from "react";

// Router mínimo sobre el History API: la app tiene pocas secciones y el
// servidor devuelve index.html para cualquier ruta sin extensión.

const listeners = new Set<() => void>();

function subscribe(fn: () => void) {
  listeners.add(fn);
  window.addEventListener("popstate", fn);
  return () => {
    listeners.delete(fn);
    window.removeEventListener("popstate", fn);
  };
}

/** Cambia la URL sin recarga y notifica a los suscriptores del router. */
export function navigate(path: string) {
  if (path === window.location.pathname) return;
  window.history.pushState(null, "", path);
  listeners.forEach((fn) => fn());
}

/** Se suscribe a cambios pushState/popstate y devuelve pathname actual. */
export function usePath(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname);
}
