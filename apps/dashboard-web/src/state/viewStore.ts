export type WidgetBindingId = string;

export interface GridGeometry {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ViewWidget {
  bindingId: WidgetBindingId;
  widgetId: string;
  title: string;
  params: Record<string, unknown>;
  hidden: boolean;
  geometry: GridGeometry;
}

export interface ViewPreset {
  id: string;
  label: string;
  patches: Record<WidgetBindingId, Partial<GridGeometry> & { hidden?: boolean }>;
}

export interface DashboardViewState {
  viewId: string;
  name: string;
  columns: number;
  widgets: Record<WidgetBindingId, ViewWidget>;
  order: WidgetBindingId[];
  presets: Record<string, ViewPreset>;
  activePresetId: string | null;
  updatedAt: string;
}

export interface ViewWidgetDraft {
  bindingId: WidgetBindingId;
  widgetId: string;
  title?: string;
  params?: Record<string, unknown>;
  geometry?: Partial<GridGeometry>;
  hidden?: boolean;
}

export interface DashboardViewStore {
  getState: () => DashboardViewState;
  subscribe: (listener: () => void) => () => void;
  addWidget: (draft: ViewWidgetDraft) => void;
  moveWidget: (bindingId: WidgetBindingId, next: Pick<GridGeometry, "x" | "y">) => void;
  resizeWidget: (bindingId: WidgetBindingId, next: Pick<GridGeometry, "w" | "h">) => void;
  hideWidget: (bindingId: WidgetBindingId, hidden: boolean) => void;
  applyPreset: (presetId: string) => void;
  registerPreset: (preset: ViewPreset) => void;
  toViewSpec: () => Record<string, unknown>;
}

const DEFAULT_COLUMNS = 12;
const MIN_WIDGET_WIDTH = 1;
const MIN_WIDGET_HEIGHT = 1;

function cloneState(state: DashboardViewState): DashboardViewState {
  const widgets: Record<WidgetBindingId, ViewWidget> = {};
  for (const [bindingId, widget] of Object.entries(state.widgets)) {
    widgets[bindingId] = {
      ...widget,
      params: { ...widget.params },
      geometry: { ...widget.geometry },
    };
  }

  const presets: Record<string, ViewPreset> = {};
  for (const [presetId, preset] of Object.entries(state.presets)) {
    presets[presetId] = {
      ...preset,
      patches: Object.fromEntries(
        Object.entries(preset.patches).map(([bindingId, patch]) => [bindingId, { ...patch }]),
      ),
    };
  }

  return {
    ...state,
    widgets,
    order: [...state.order],
    presets,
  };
}

function normalizeInt(value: number, minimum: number): number {
  if (!Number.isFinite(value)) {
    return minimum;
  }
  return Math.max(Math.trunc(value), minimum);
}

function clampGeometry(geometry: GridGeometry, columns: number): GridGeometry {
  const width = Math.min(normalizeInt(geometry.w, MIN_WIDGET_WIDTH), columns);
  const height = normalizeInt(geometry.h, MIN_WIDGET_HEIGHT);
  const x = Math.max(0, Math.trunc(geometry.x));
  const y = Math.max(0, Math.trunc(geometry.y));

  const boundedX = x + width > columns ? Math.max(columns - width, 0) : x;

  return { x: boundedX, y, w: width, h: height };
}

function nextAutoGeometry(state: DashboardViewState): GridGeometry {
  const occupied = state.order
    .map((bindingId) => state.widgets[bindingId])
    .filter((widget): widget is ViewWidget => Boolean(widget));

  if (occupied.length === 0) {
    return { x: 0, y: 0, w: 6, h: 6 };
  }

  const lowest = occupied.reduce((current, widget) => {
    const bottom = widget.geometry.y + widget.geometry.h;
    return bottom > current ? bottom : current;
  }, 0);

  return { x: 0, y: lowest, w: 6, h: 6 };
}

function ensureWidget(state: DashboardViewState, bindingId: WidgetBindingId): ViewWidget {
  const widget = state.widgets[bindingId];
  if (!widget) {
    throw new Error(`Unknown widget binding: ${bindingId}`);
  }
  return widget;
}

function defaultState(): DashboardViewState {
  return {
    viewId: "view-local-default",
    name: "Workspace",
    columns: DEFAULT_COLUMNS,
    widgets: {},
    order: [],
    presets: {},
    activePresetId: null,
    updatedAt: new Date().toISOString(),
  };
}

export function createViewStore(initial?: Partial<DashboardViewState>): DashboardViewStore {
  let state: DashboardViewState = {
    ...defaultState(),
    ...initial,
    widgets: { ...(initial?.widgets ?? {}) },
    order: [...(initial?.order ?? [])],
    presets: { ...(initial?.presets ?? {}) },
    activePresetId: initial?.activePresetId ?? null,
    updatedAt: initial?.updatedAt ?? new Date().toISOString(),
  };

  const listeners = new Set<() => void>();

  const notify = () => {
    for (const listener of listeners) {
      listener();
    }
  };

  const update = (updater: (current: DashboardViewState) => DashboardViewState): void => {
    const next = updater(cloneState(state));
    state = {
      ...next,
      updatedAt: new Date().toISOString(),
    };
    notify();
  };

  return {
    getState: () => cloneState(state),

    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },

    addWidget: (draft: ViewWidgetDraft) => {
      update((current) => {
        if (current.widgets[draft.bindingId]) {
          throw new Error(`Widget binding already exists: ${draft.bindingId}`);
        }

        const columns = current.columns;
        const geometry = clampGeometry(
          {
            ...nextAutoGeometry(current),
            ...(draft.geometry ?? {}),
          },
          columns,
        );

        current.widgets[draft.bindingId] = {
          bindingId: draft.bindingId,
          widgetId: draft.widgetId,
          title: draft.title ?? draft.widgetId,
          params: { ...(draft.params ?? {}) },
          hidden: Boolean(draft.hidden),
          geometry,
        };
        current.order.push(draft.bindingId);
        current.activePresetId = null;
        return current;
      });
    },

    moveWidget: (bindingId: WidgetBindingId, next: Pick<GridGeometry, "x" | "y">) => {
      update((current) => {
        const widget = ensureWidget(current, bindingId);
        widget.geometry = clampGeometry(
          {
            ...widget.geometry,
            ...next,
          },
          current.columns,
        );
        current.activePresetId = null;
        return current;
      });
    },

    resizeWidget: (bindingId: WidgetBindingId, next: Pick<GridGeometry, "w" | "h">) => {
      update((current) => {
        const widget = ensureWidget(current, bindingId);
        widget.geometry = clampGeometry(
          {
            ...widget.geometry,
            ...next,
          },
          current.columns,
        );
        current.activePresetId = null;
        return current;
      });
    },

    hideWidget: (bindingId: WidgetBindingId, hidden: boolean) => {
      update((current) => {
        const widget = ensureWidget(current, bindingId);
        widget.hidden = hidden;
        return current;
      });
    },

    applyPreset: (presetId: string) => {
      update((current) => {
        const preset = current.presets[presetId];
        if (!preset) {
          throw new Error(`Unknown preset: ${presetId}`);
        }

        for (const [bindingId, patch] of Object.entries(preset.patches)) {
          const widget = current.widgets[bindingId];
          if (!widget) {
            continue;
          }

          widget.geometry = clampGeometry(
            {
              ...widget.geometry,
              ...patch,
            },
            current.columns,
          );

          if (typeof patch.hidden === "boolean") {
            widget.hidden = patch.hidden;
          }
        }

        current.activePresetId = presetId;
        return current;
      });
    },

    registerPreset: (preset: ViewPreset) => {
      update((current) => {
        current.presets[preset.id] = {
          ...preset,
          patches: Object.fromEntries(
            Object.entries(preset.patches).map(([bindingId, patch]) => [bindingId, { ...patch }]),
          ),
        };
        return current;
      });
    },

    toViewSpec: () => {
      const snapshot = cloneState(state);
      return {
        schema_version: "1.0",
        name: snapshot.name,
        scope: "personal",
        owner: {
          user_id: "local-user",
          role: "Editor",
        },
        layout: {
          columns: snapshot.columns,
          row_height: 32,
          items: snapshot.order.map((bindingId) => {
            const widget = snapshot.widgets[bindingId];
            return {
              binding_id: bindingId,
              x: widget.geometry.x,
              y: widget.geometry.y,
              w: widget.geometry.w,
              h: widget.geometry.h,
            };
          }),
        },
        filters: {
          time_bucket: "day",
        },
        widgets: snapshot.order.map((bindingId) => {
          const widget = snapshot.widgets[bindingId];
          return {
            binding_id: bindingId,
            widget_id: widget.widgetId,
            title: widget.title,
            params: { ...widget.params },
            overrides: {
              hidden: widget.hidden,
            },
          };
        }),
      };
    },
  };
}

export function createSeededViewStore(): DashboardViewStore {
  const store = createViewStore({
    viewId: "view-team-default",
    name: "Team Overview",
  });

  store.addWidget({
    bindingId: "widget-provider-tokens",
    widgetId: "provider-token-split",
    title: "Provider Token Split",
    params: { time_bucket: "day" },
    geometry: { x: 0, y: 0, w: 8, h: 6 },
  });

  store.addWidget({
    bindingId: "widget-project-cost",
    widgetId: "project-cost-variance",
    title: "Project Cost Variance",
    params: { time_bucket: "day" },
    geometry: { x: 8, y: 0, w: 4, h: 6 },
  });

  store.registerPreset({
    id: "focus-cost",
    label: "Focus Cost",
    patches: {
      "widget-provider-tokens": { x: 0, y: 0, w: 5, h: 5, hidden: true },
      "widget-project-cost": { x: 0, y: 0, w: 12, h: 7, hidden: false },
    },
  });

  store.registerPreset({
    id: "balanced",
    label: "Balanced",
    patches: {
      "widget-provider-tokens": { x: 0, y: 0, w: 8, h: 6, hidden: false },
      "widget-project-cost": { x: 8, y: 0, w: 4, h: 6, hidden: false },
    },
  });

  return store;
}
