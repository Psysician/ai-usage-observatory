import { useEffect, useMemo, useState } from "react";

import { GridEditor } from "../../components/layout/GridEditor";
import {
  createSeededViewStore,
  type DashboardViewState,
} from "../../state/viewStore";
import type { WidgetPayloadEnvelope } from "../../components/widgets/WidgetShell";

function payloadFor(widgetId: string): WidgetPayloadEnvelope {
  if (widgetId === "project-cost-variance") {
    return {
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

const ADDABLE_WIDGET_IDS = [
  "provider-token-split",
  "project-cost-variance",
  "memory-churn-overview",
];

export default function DashboardPage(): JSX.Element {
  const store = useMemo(() => createSeededViewStore(), []);
  const [state, setState] = useState<DashboardViewState>(() => store.getState());
  const [nextWidgetCounter, setNextWidgetCounter] = useState(1);

  useEffect(() => {
    return store.subscribe(() => {
      setState(store.getState());
    });
  }, [store]);

  const widgetPayloads = useMemo(() => {
    const map: Record<string, WidgetPayloadEnvelope> = {};
    for (const bindingId of state.order) {
      const widget = state.widgets[bindingId];
      if (!widget) {
        continue;
      }
      map[bindingId] = payloadFor(widget.widgetId);
    }
    return map;
  }, [state.order, state.widgets]);

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
        renderBody={(widget) => (
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
        )}
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
