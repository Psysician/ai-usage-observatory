import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

import {
  createSeededViewStore,
  type DashboardViewState,
} from "../../src/state/viewStore";
import {
  deriveAttributionConfidencePct,
  deriveFreshnessAgeSeconds,
} from "../../src/components/widgets/WidgetShell";

function widget(state: DashboardViewState, bindingId: string) {
  const item = state.widgets[bindingId];
  if (!item) {
    throw new Error(`Missing widget ${bindingId}`);
  }
  return item;
}

function runShareExport(viewRecord: Record<string, unknown>, allowlist: string[] = []): Record<string, unknown> {
  const repoRoot = resolve(__dirname, "../../../..");
  const script = `
import json
import sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
root = Path(payload["repo_root"])
sys.path.insert(0, str(root / "apps" / "dashboard-sync" / "src"))

from sync.share_service import build_team_share_export

exported = build_team_share_export(
    payload["view_record"],
    allowlist=payload["allowlist"],
    shared_by="e2e-test",
)
print(json.dumps(exported, sort_keys=True))
`;

  const stdout = execFileSync("python3", ["-c", script], {
    cwd: repoRoot,
    encoding: "utf-8",
    input: JSON.stringify({
      repo_root: repoRoot,
      view_record: viewRecord,
      allowlist,
    }),
  });

  return JSON.parse(stdout) as Record<string, unknown>;
}

test.describe("customization and share", () => {
  test("workspace supports add/move/resize/hide/preset actions", async () => {
    const store = createSeededViewStore();

    store.addWidget({
      bindingId: "widget-memory",
      widgetId: "memory-churn-overview",
      title: "Memory Churn Overview",
      params: { window: "week" },
      geometry: { x: 2, y: 6, w: 6, h: 4 },
    });

    store.moveWidget("widget-memory", { x: 4, y: 7 });
    store.resizeWidget("widget-memory", { w: 5, h: 6 });
    store.hideWidget("widget-memory", true);
    store.applyPreset("balanced");

    const snapshot = store.getState();
    const memory = widget(snapshot, "widget-memory");
    const provider = widget(snapshot, "widget-provider-tokens");

    expect(memory.geometry.x).toBe(4);
    expect(memory.geometry.y).toBe(7);
    expect(memory.geometry.w).toBe(5);
    expect(memory.geometry.h).toBe(6);
    expect(memory.hidden).toBe(true);

    expect(provider.hidden).toBe(false);
    expect(snapshot.activePresetId).toBe("balanced");

    const freshness = deriveFreshnessAgeSeconds(
      {
        auditability: {
          freshness: {
            staleness_seconds: 90,
          },
        },
      },
      new Date("2026-03-01T00:00:00.000Z"),
    );
    const confidence = deriveAttributionConfidencePct({
      auditability: {
        attribution_coverage_pct: 93.3,
      },
    });

    expect(freshness).toBe(90);
    expect(confidence).toBe(93.3);
  });

  test("team share export omits local sensitive identifiers unless allowlisted", async () => {
    const sharedView = {
      view_id: "view-team-01",
      created_by: "alice-local",
      updated_by: "alice-local",
      local_machine_id: "machine-42",
      spec: {
        schema_version: "1.0",
        scope: "team",
        owner: {
          user_id: "alice-local",
          role: "Editor",
        },
        layout: {
          columns: 12,
          row_height: 32,
          items: [
            {
              binding_id: "widget-main",
              x: 0,
              y: 0,
              w: 12,
              h: 6,
            },
          ],
        },
        filters: {
          time_bucket: "day",
          project_id: "project-alpha",
          workspace_path: "/home/alice/workspace",
        },
        widgets: [
          {
            binding_id: "widget-main",
            widget_id: "provider-token-split",
            params: {
              time_bucket: "day",
            },
            overrides: {
              hidden: false,
            },
          },
        ],
      },
    } as const;

    const redacted = runShareExport(sharedView);
    const redactedView = redacted.view as Record<string, unknown>;
    const redactedSpec = redactedView.spec as Record<string, unknown>;
    const redactedOwner = redactedSpec.owner as Record<string, unknown>;
    const redactedFilters = redactedSpec.filters as Record<string, unknown>;

    expect(redactedView.created_by).toBeUndefined();
    expect(redactedView.updated_by).toBeUndefined();
    expect(redactedView.local_machine_id).toBeUndefined();
    expect(redactedOwner.user_id).toBeUndefined();
    expect(redactedFilters.workspace_path).toBeUndefined();

    const allowlisted = runShareExport(sharedView, ["spec.owner.user_id"]);
    const allowlistedView = allowlisted.view as Record<string, unknown>;
    const allowlistedSpec = allowlistedView.spec as Record<string, unknown>;
    const allowlistedOwner = allowlistedSpec.owner as Record<string, unknown>;

    expect(allowlistedOwner.user_id).toBe("alice-local");
    expect(allowlistedView.created_by).toBeUndefined();
    expect(allowlistedView.local_machine_id).toBeUndefined();

    const redactionMeta = allowlisted.redaction as Record<string, unknown>;
    const allowlistedPaths = redactionMeta.allowlisted_sensitive_paths as string[];
    expect(allowlistedPaths).toContain("spec.owner.user_id");
  });
});
