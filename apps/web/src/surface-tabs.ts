/**
 * Console surface tabs: one floating panel at a time (M8 batch F surfaces).
 *
 * `#tab-<id>` toggles `#panel-<id>`: clicking the active tab closes it, so the
 * reader can reclaim the whole PDF width without leaving the console. Panels
 * live in `#surface-panels` in DOM order upload → select → history → status →
 * inspector; that order is the stacking order the layout relies on.
 */
import { requiredElement } from "./reader-dom.js";

export type SurfaceId = "upload" | "select" | "history" | "status";

export type SurfaceTabs = {
  active: SurfaceId | null;
  open(id: SurfaceId): void;
  close(): void;
  onChange(fn: (active: SurfaceId | null) => void): void;
};

const SURFACE_IDS: SurfaceId[] = ["upload", "select", "history", "status"];

export function bootSurfaceTabs(): SurfaceTabs {
  const surfaces = SURFACE_IDS.map((id) => ({
    id,
    panel: requiredElement<HTMLElement>(`#panel-${id}`),
    tab: requiredElement<HTMLButtonElement>(`#tab-${id}`),
  }));
  const listeners: ((active: SurfaceId | null) => void)[] = [];
  const apply = (): void => {
    for (const surface of surfaces) {
      surface.panel.hidden = surface.id !== api.active;
      surface.tab.setAttribute("aria-selected", String(surface.id === api.active));
    }
  };
  const api: SurfaceTabs = {
    active: null,
    open(id: SurfaceId): void {
      if (api.active === id) return;
      api.active = id;
      apply();
      for (const listener of listeners) listener(api.active);
    },
    close(): void {
      if (api.active === null) return;
      api.active = null;
      apply();
      for (const listener of listeners) listener(null);
    },
    onChange(fn): void {
      listeners.push(fn);
      fn(api.active);
    },
  };
  for (const surface of surfaces) {
    surface.tab.addEventListener("click", () => {
      if (api.active === surface.id) api.close();
      else api.open(surface.id);
    });
  }
  apply();
  return api;
}
