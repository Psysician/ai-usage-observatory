import type { ReactNode } from "react";

import {
  type DashboardViewState,
  type ViewWidget,
  type WidgetBindingId,
} from "../../state/viewStore";
import {
  WidgetShell,
  type WidgetPayloadEnvelope,
} from "../widgets/WidgetShell";

export interface GridEditorProps {
  state: DashboardViewState;
  payloadByBindingId?: Record<WidgetBindingId, WidgetPayloadEnvelope | undefined>;
  onMoveWidget: (bindingId: WidgetBindingId, deltaX: number, deltaY: number) => void;
  onResizeWidget: (bindingId: WidgetBindingId, deltaW: number, deltaH: number) => void;
  onHideWidget: (bindingId: WidgetBindingId, hidden: boolean) => void;
  renderBody?: (widget: ViewWidget) => ReactNode;
}

function rowEnd(widget: ViewWidget): number {
  return widget.geometry.y + widget.geometry.h;
}

function visibleWidgets(state: DashboardViewState): ViewWidget[] {
  return state.order
    .map((bindingId) => state.widgets[bindingId])
    .filter((widget): widget is ViewWidget => Boolean(widget) && !widget.hidden)
    .sort((left, right) => rowEnd(left) - rowEnd(right));
}

function hiddenWidgets(state: DashboardViewState): ViewWidget[] {
  return state.order
    .map((bindingId) => state.widgets[bindingId])
    .filter((widget): widget is ViewWidget => Boolean(widget) && widget.hidden);
}

function actionButton(
  label: string,
  onClick: () => void,
  testId: string,
): JSX.Element {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      style={{
        border: "1px solid #d0d7de",
        borderRadius: "4px",
        padding: "0.2rem 0.5rem",
        background: "#f7fafc",
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

export function GridEditor(props: GridEditorProps): JSX.Element {
  const visible = visibleWidgets(props.state);
  const hidden = hiddenWidgets(props.state);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div
        data-testid="grid-editor"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${props.state.columns}, minmax(0, 1fr))`,
          gridAutoRows: "36px",
          gap: "0.6rem",
          alignItems: "stretch",
        }}
      >
        {visible.map((widget) => {
          const payload = props.payloadByBindingId?.[widget.bindingId];
          return (
            <div
              key={widget.bindingId}
              data-testid={`widget-${widget.bindingId}`}
              style={{
                gridColumn: `${widget.geometry.x + 1} / span ${widget.geometry.w}`,
                gridRow: `${widget.geometry.y + 1} / span ${widget.geometry.h}`,
                minHeight: "100px",
              }}
            >
              <WidgetShell
                title={widget.title}
                widgetId={widget.widgetId}
                payload={payload}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "0.5rem",
                    marginBottom: "0.6rem",
                    flexWrap: "wrap",
                  }}
                >
                  <small data-testid={`geometry-${widget.bindingId}`}>
                    x={widget.geometry.x} y={widget.geometry.y} w={widget.geometry.w} h={widget.geometry.h}
                  </small>
                  <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                    {actionButton("←", () => props.onMoveWidget(widget.bindingId, -1, 0), `${widget.bindingId}-move-left`)}
                    {actionButton("→", () => props.onMoveWidget(widget.bindingId, 1, 0), `${widget.bindingId}-move-right`)}
                    {actionButton("↑", () => props.onMoveWidget(widget.bindingId, 0, -1), `${widget.bindingId}-move-up`)}
                    {actionButton("↓", () => props.onMoveWidget(widget.bindingId, 0, 1), `${widget.bindingId}-move-down`)}
                    {actionButton("W+", () => props.onResizeWidget(widget.bindingId, 1, 0), `${widget.bindingId}-resize-w-plus`)}
                    {actionButton("W-", () => props.onResizeWidget(widget.bindingId, -1, 0), `${widget.bindingId}-resize-w-minus`)}
                    {actionButton("H+", () => props.onResizeWidget(widget.bindingId, 0, 1), `${widget.bindingId}-resize-h-plus`)}
                    {actionButton("H-", () => props.onResizeWidget(widget.bindingId, 0, -1), `${widget.bindingId}-resize-h-minus`)}
                    {actionButton("Hide", () => props.onHideWidget(widget.bindingId, true), `${widget.bindingId}-hide`)}
                  </div>
                </div>
                <div>{props.renderBody ? props.renderBody(widget) : null}</div>
              </WidgetShell>
            </div>
          );
        })}
      </div>

      {hidden.length > 0 ? (
        <aside aria-label="Hidden widgets" style={{ borderTop: "1px solid #eaeef2", paddingTop: "0.5rem" }}>
          <strong style={{ display: "block", marginBottom: "0.4rem" }}>Hidden widgets</strong>
          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
            {hidden.map((widget) => (
              <button
                key={widget.bindingId}
                type="button"
                data-testid={`${widget.bindingId}-show`}
                onClick={() => props.onHideWidget(widget.bindingId, false)}
                style={{
                  border: "1px solid #d0d7de",
                  borderRadius: "999px",
                  padding: "0.2rem 0.6rem",
                  background: "#ffffff",
                }}
              >
                Show {widget.title}
              </button>
            ))}
          </div>
        </aside>
      ) : null}
    </div>
  );
}
