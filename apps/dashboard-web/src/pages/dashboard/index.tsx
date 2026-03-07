import { useEffect, useMemo, useState } from "react";

import { GridEditor } from "../../components/layout/GridEditor";
import {
  createSeededViewStore,
  type DashboardViewState,
  type ViewWidget,
} from "../../state/viewStore";
import {
  widgetPayloadFromUnknown,
  type WidgetPayloadEnvelope,
} from "../../components/widgets/WidgetShell";

function fallbackPayloadFor(widgetId: string): WidgetPayloadEnvelope {
  if (widgetId === "project-cost-variance") {
    return {
      data: { projects: [] },
      generated_at: "2026-03-01T00:00:00+00:00",
      auditability: {
        freshness: {
          staleness_seconds: 960,
          source_watermark: "2026-02-29T23:44:00+00:00",
        },
        attribution_coverage_pct: 93.2,
      },
    };
  }

  if (widgetId === "memory-churn-overview") {
    return {
      data: { projects: [], freshness: { freshness_state: "partial" } },
      generated_at: "2026-03-01T00:00:00+00:00",
      auditability: {
        freshness: {
          staleness_seconds: 220,
          source_watermark: "2026-02-29T23:56:20+00:00",
        },
        attribution_coverage_pct: 98.7,
      },
    };
  }

  return {
    data: { provider_split: [] },
    generated_at: "2026-03-01T00:00:00+00:00",
    auditability: {
      freshness: {
        staleness_seconds: 125,
        source_watermark: "2026-02-29T23:57:55+00:00",
      },
      attribution_coverage_pct: 97.5,
    },
  };
}

function labelFor(widgetId: string): string {
  if (widgetId === "project-cost-variance") {
    return "Project Cost Variance";
  }
  if (widgetId === "memory-churn-overview") {
    return "Memory Churn Overview";
  }
  return "Provider Token Split";
}

function apiBaseUrl(): string {
  if (typeof window === "undefined") {
    return "";
  }
  const value = (window as Window & { __AIO_API_BASE__?: string }).__AIO_API_BASE__;
  if (typeof value === "string" && value.trim().length > 0) {
    return value.trim().replace(/\/+$/, "");
  }
  return "";
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return value as Record<string, unknown>;
}

function asRows(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
}

function asNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function formatUsd(value: number | null): string {
  if (value === null) {
    return "n/a";
  }
  return `$${value.toFixed(2)}`;
}

function widgetRequest(widget: ViewWidget): {
  url: string;
  init?: RequestInit;
  drilldownPath: string;
} | null {
  const timeBucket =
    typeof widget.params.time_bucket === "string" && widget.params.time_bucket
      ? widget.params.time_bucket
      : "day";
  const base = apiBaseUrl();

  if (widget.widgetId === "provider-token-split") {
    return {
      url: `${base}/metrics?time_bucket=${encodeURIComponent(timeBucket)}`,
      drilldownPath: "/metrics",
    };
  }

  if (widget.widgetId === "project-cost-variance") {
    return {
      url: `${base}/projects?time_bucket=${encodeURIComponent(timeBucket)}`,
      drilldownPath: "/projects",
    };
  }

  if (widget.widgetId === "memory-churn-overview") {
    return {
      url: `${base}/memory/insights`,
      init: {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ memory_file_paths: [] }),
      },
      drilldownPath: "/memory/insights",
    };
  }
  return null;
}

async function fetchWidgetPayload(widget: ViewWidget): Promise<WidgetPayloadEnvelope | null> {
  const request = widgetRequest(widget);
  if (!request) {
    return null;
  }

  try {
    const response = await fetch(request.url, request.init);
    if (!response.ok) {
      return null;
    }
    const root = (await response.json()) as unknown;
    const envelope = widgetPayloadFromUnknown(root);
    if (!envelope.provenance) {
      envelope.provenance = {
        widget_id: widget.widgetId,
        catalog_version: "runtime",
      };
    }
    if (!envelope.drilldown) {
      envelope.drilldown = {
        path: request.drilldownPath,
        label: `${widget.title} details`,
        params: { ...widget.params },
      };
    }
    return envelope;
  } catch {
    return null;
  }
}

const ADDABLE_WIDGET_IDS = [
  "provider-token-split",
  "project-cost-variance",
  "memory-churn-overview",
];
const LIVE_REFRESH_INTERVAL_MS = 15000;

export default function DashboardPage(): JSX.Element {
  const store = useMemo(() => createSeededViewStore(), []);
  const [state, setState] = useState<DashboardViewState>(() => store.getState());
  const [nextWidgetCounter, setNextWidgetCounter] = useState(1);
  const [livePayloads, setLivePayloads] = useState<Record<string, WidgetPayloadEnvelope>>({});

  useEffect(() => {
    return store.subscribe(() => {
      setState(store.getState());
    });
  }, [store]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const liveWidgets = state.order
      .map((bindingId) => ({
        bindingId,
        widget: state.widgets[bindingId],
      }))
      .filter(
        (
          entry,
        ): entry is { bindingId: string; widget: NonNullable<DashboardViewState["widgets"][string]> } =>
          Boolean(entry.widget),
      );

    const load = async () => {
      const results = await Promise.all(
        liveWidgets.map(async ({ bindingId, widget }) => {
          const payload = await fetchWidgetPayload(widget);
          return [bindingId, payload] as const;
        }),
      );
      if (cancelled) {
        return;
      }
      setLivePayloads((previous) => {
        const next = { ...previous };
        for (const [bindingId, payload] of results) {
          if (payload) {
            next[bindingId] = payload;
          }
        }
        return next;
      });
    };

    void load();
    timer = window.setInterval(() => {
      void load();
    }, LIVE_REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearInterval(timer);
      }
    };
  }, [state.order, state.widgets]);

  const widgetPayloads = useMemo(() => {
    const map: Record<string, WidgetPayloadEnvelope> = {};
    for (const bindingId of state.order) {
      const widget = state.widgets[bindingId];
      if (!widget) {
        continue;
      }
      if (livePayloads[bindingId]) {
        map[bindingId] = livePayloads[bindingId];
        continue;
      }
      map[bindingId] = fallbackPayloadFor(widget.widgetId);
    }
    return map;
  }, [livePayloads, state.order, state.widgets]);

  const renderWidgetBody = (widget: ViewWidget): JSX.Element => {
    const payload = widgetPayloads[widget.bindingId];
    const data = asRecord(payload?.data);

    if (widget.widgetId === "provider-token-split") {
      const rows = asRows(data.provider_split);
      const totalTokens = rows.reduce((acc, row) => acc + (asNumber(row.tokens_total) ?? 0), 0);
      const providers = rows
        .slice(0, 3)
        .map((row) => `${String(row.provider ?? "unknown")}: ${Math.trunc(asNumber(row.tokens_total) ?? 0)}`)
        .join(" | ");
      return (
        <div data-testid={`widget-body-${widget.bindingId}`} style={{ fontSize: "0.82rem", color: "#344054" }}>
          <div><strong>Total tokens:</strong> {Math.trunc(totalTokens)}</div>
          <div><strong>Providers:</strong> {providers || "no rows"}</div>
          <div><strong>Drilldown:</strong> {payload?.drilldown?.path ?? "n/a"}</div>
        </div>
      );
    }

    if (widget.widgetId === "project-cost-variance") {
      const projects = asRows(data.projects).slice(0, 4);
      return (
        <div data-testid={`widget-body-${widget.bindingId}`} style={{ fontSize: "0.82rem", color: "#344054" }}>
          <div><strong>Projects:</strong> {projects.length}</div>
          {projects.map((row, index) => {
            const name = String(row.project_id ?? `project-${index + 1}`);
            const variance = asNumber(row.cost_variance_usd);
            return (
              <div key={`${widget.bindingId}-${name}-${index}`}>
                {name}: {formatUsd(variance)}
              </div>
            );
          })}
          <div><strong>Drilldown:</strong> {payload?.drilldown?.path ?? "n/a"}</div>
        </div>
      );
    }

    if (widget.widgetId === "memory-churn-overview") {
      const projects = asRows(data.projects);
      const freshness = asRecord(data.freshness);
      return (
        <div data-testid={`widget-body-${widget.bindingId}`} style={{ fontSize: "0.82rem", color: "#344054" }}>
          <div><strong>Tracked projects:</strong> {projects.length}</div>
          <div><strong>Freshness:</strong> {String(freshness.freshness_state ?? "partial")}</div>
          <div><strong>Unavailable files:</strong> {Math.trunc(asNumber(freshness.unavailable_files) ?? 0)}</div>
          <div><strong>Drilldown:</strong> {payload?.drilldown?.path ?? "n/a"}</div>
        </div>
      );
    }

    return (
      <pre
        data-testid={`widget-body-${widget.bindingId}`}
        style={{
          margin: 0,
          whiteSpace: "pre-wrap",
          fontSize: "0.8rem",
          color: "#344054",
        }}
      >
        {JSON.stringify(widget.params, null, 2)}
      </pre>
    );
  };

  const addWidget = () => {
    const widgetId = ADDABLE_WIDGET_IDS[nextWidgetCounter % ADDABLE_WIDGET_IDS.length];
    const bindingId = `widget-custom-${nextWidgetCounter}`;

    store.addWidget({
      bindingId,
      widgetId,
      title: labelFor(widgetId),
      params: { time_bucket: "day" },
      geometry: { x: 0, y: 0, w: 6, h: 5 },
    });

    setNextWidgetCounter((value) => value + 1);
  };

  return (
    <main
      style={{
        margin: "0 auto",
        maxWidth: "1240px",
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.9rem",
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", flexWrap: "wrap" }}>
        <div>
          <h1 style={{ margin: 0 }}>Dashboard Workspace</h1>
          <small data-testid="workspace-updated-at">
            Updated {new Date(state.updatedAt).toLocaleTimeString()}
          </small>
        </div>
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
          <button type="button" data-testid="add-widget" onClick={addWidget}>
            Add Widget
          </button>
          <button
            type="button"
            data-testid="preset-balanced"
            onClick={() => store.applyPreset("balanced")}
          >
            Preset: Balanced
          </button>
          <button
            type="button"
            data-testid="preset-focus-cost"
            onClick={() => store.applyPreset("focus-cost")}
          >
            Preset: Focus Cost
          </button>
        </div>
      </header>

      <GridEditor
        state={state}
        payloadByBindingId={widgetPayloads}
        onMoveWidget={(bindingId, deltaX, deltaY) => {
          const widget = state.widgets[bindingId];
          if (!widget) {
            return;
          }
          store.moveWidget(bindingId, {
            x: widget.geometry.x + deltaX,
            y: widget.geometry.y + deltaY,
          });
        }}
        onResizeWidget={(bindingId, deltaW, deltaH) => {
          const widget = state.widgets[bindingId];
          if (!widget) {
            return;
          }
          store.resizeWidget(bindingId, {
            w: widget.geometry.w + deltaW,
            h: widget.geometry.h + deltaH,
          });
        }}
        onHideWidget={(bindingId, hidden) => {
          store.hideWidget(bindingId, hidden);
        }}
        renderBody={renderWidgetBody}
      />

      <aside style={{ borderTop: "1px solid #eaeef2", paddingTop: "0.75rem" }}>
        <strong>Declarative View Snapshot</strong>
        <pre
          data-testid="view-spec-snapshot"
          style={{
            margin: "0.5rem 0 0",
            padding: "0.75rem",
            borderRadius: "8px",
            background: "#f8fafc",
            fontSize: "0.75rem",
            overflowX: "auto",
          }}
        >
          {JSON.stringify(store.toViewSpec(), null, 2)}
        </pre>
      </aside>
    </main>
  );
}
