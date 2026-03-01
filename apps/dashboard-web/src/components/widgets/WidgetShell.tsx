import type { ReactNode } from "react";

export interface WidgetPayloadEnvelope {
  generated_at?: string;
  auditability?: {
    freshness?: {
      staleness_seconds?: number;
      source_watermark?: string | null;
      generated_at?: string;
    };
    attribution_coverage_pct?: number;
    attribution_confidence_pct?: number;
  };
  attribution_confidence_pct?: number;
}

export interface WidgetShellProps {
  title: string;
  widgetId: string;
  payload?: WidgetPayloadEnvelope;
  now?: Date;
  children?: ReactNode;
}

function asFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return value as Record<string, unknown>;
}

function parseTimestamp(value: unknown): number | null {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : null;
}

function normalizePercent(value: number | null): number | null {
  if (value === null) {
    return null;
  }

  const normalized = value <= 1 ? value * 100 : value;
  const bounded = Math.max(0, Math.min(100, normalized));
  return Math.round(bounded * 10) / 10;
}

function formatAge(ageSeconds: number | null): string {
  if (ageSeconds === null) {
    return "unknown";
  }
  if (ageSeconds < 60) {
    return `${Math.trunc(ageSeconds)}s ago`;
  }
  if (ageSeconds < 3600) {
    return `${Math.trunc(ageSeconds / 60)}m ago`;
  }
  if (ageSeconds < 86400) {
    return `${Math.trunc(ageSeconds / 3600)}h ago`;
  }
  return `${Math.trunc(ageSeconds / 86400)}d ago`;
}

export function deriveFreshnessAgeSeconds(
  payload: WidgetPayloadEnvelope | undefined,
  now: Date = new Date(),
): number | null {
  if (!payload) {
    return null;
  }

  const stalenessSeconds = asFiniteNumber(payload.auditability?.freshness?.staleness_seconds);
  if (stalenessSeconds !== null) {
    return Math.max(stalenessSeconds, 0);
  }

  const generatedAtMs = parseTimestamp(payload.auditability?.freshness?.generated_at) ?? parseTimestamp(payload.generated_at);
  const watermarkMs = parseTimestamp(payload.auditability?.freshness?.source_watermark);

  if (generatedAtMs !== null && watermarkMs !== null) {
    return Math.max(Math.trunc((generatedAtMs - watermarkMs) / 1000), 0);
  }

  if (watermarkMs !== null) {
    return Math.max(Math.trunc((now.getTime() - watermarkMs) / 1000), 0);
  }

  return null;
}

export function deriveAttributionConfidencePct(
  payload: WidgetPayloadEnvelope | undefined,
): number | null {
  if (!payload) {
    return null;
  }

  const value =
    asFiniteNumber(payload.auditability?.attribution_confidence_pct) ??
    asFiniteNumber(payload.auditability?.attribution_coverage_pct) ??
    asFiniteNumber(payload.attribution_confidence_pct);

  return normalizePercent(value);
}

export function WidgetShell(props: WidgetShellProps): JSX.Element {
  const ageSeconds = deriveFreshnessAgeSeconds(props.payload, props.now ?? new Date());
  const confidencePct = deriveAttributionConfidencePct(props.payload);

  return (
    <section
      aria-label={`${props.title} widget`}
      data-widget-id={props.widgetId}
      style={{
        border: "1px solid #ccd5df",
        borderRadius: "8px",
        padding: "0.75rem",
        background: "#ffffff",
        boxShadow: "0 2px 6px rgba(16, 24, 40, 0.06)",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.5rem",
          flexWrap: "wrap",
        }}
      >
        <strong>{props.title}</strong>
        <div style={{ display: "flex", gap: "0.5rem", fontSize: "0.8rem" }}>
          <span
            data-testid={`${props.widgetId}-freshness`}
            style={{
              borderRadius: "999px",
              padding: "0.2rem 0.55rem",
              background: "#edf5ff",
              color: "#0b4f91",
            }}
          >
            Freshness {formatAge(ageSeconds)}
          </span>
          <span
            data-testid={`${props.widgetId}-confidence`}
            style={{
              borderRadius: "999px",
              padding: "0.2rem 0.55rem",
              background: "#f2fbe8",
              color: "#385d0a",
            }}
          >
            Attribution {confidencePct === null ? "unknown" : `${confidencePct}%`}
          </span>
        </div>
      </header>
      <div>{props.children}</div>
    </section>
  );
}

export function readAuditabilitySnapshot(payload: WidgetPayloadEnvelope | undefined): {
  freshnessAgeSeconds: number | null;
  attributionConfidencePct: number | null;
} {
  return {
    freshnessAgeSeconds: deriveFreshnessAgeSeconds(payload),
    attributionConfidencePct: deriveAttributionConfidencePct(payload),
  };
}

export function widgetPayloadFromUnknown(input: unknown): WidgetPayloadEnvelope {
  const root = asRecord(input);
  return {
    generated_at: typeof root.generated_at === "string" ? root.generated_at : undefined,
    attribution_confidence_pct: asFiniteNumber(root.attribution_confidence_pct) ?? undefined,
    auditability: {
      freshness: {
        staleness_seconds: asFiniteNumber(asRecord(asRecord(root.auditability).freshness).staleness_seconds) ?? undefined,
        source_watermark:
          typeof asRecord(asRecord(root.auditability).freshness).source_watermark === "string"
            ? (asRecord(asRecord(root.auditability).freshness).source_watermark as string)
            : null,
        generated_at:
          typeof asRecord(asRecord(root.auditability).freshness).generated_at === "string"
            ? (asRecord(asRecord(root.auditability).freshness).generated_at as string)
            : undefined,
      },
      attribution_coverage_pct:
        asFiniteNumber(asRecord(root.auditability).attribution_coverage_pct) ?? undefined,
      attribution_confidence_pct:
        asFiniteNumber(asRecord(root.auditability).attribution_confidence_pct) ?? undefined,
    },
  };
}
