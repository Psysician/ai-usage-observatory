declare module "@playwright/test" {
  export const test: {
    describe: (name: string, callback: () => void) => void;
    step?: (name: string, body: () => Promise<void> | void) => Promise<void>;
    (name: string, callback: () => Promise<void> | void): void;
  };
  export const expect: (actual: unknown) => {
    toBe: (expected: unknown) => void;
    toContain: (expected: unknown) => void;
    toBeUndefined: () => void;
  };
}

declare module "node:child_process" {
  export function execFileSync(
    file: string,
    args?: readonly string[],
    options?: {
      cwd?: string;
      encoding?: string;
      input?: string;
    },
  ): string;
}

declare module "node:path" {
  export function resolve(...paths: string[]): string;
}

declare const __dirname: string;
