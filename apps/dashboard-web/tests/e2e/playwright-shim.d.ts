declare module "@playwright/test" {
  export interface Locator {}
  export interface Page {
    goto: (url: string) => Promise<void>;
    getByTestId: (id: string) => Locator;
  }

  export interface TestContext {
    page: Page;
  }

  export const test: {
    describe: (name: string, callback: () => void) => void;
    step?: (name: string, body: () => Promise<void> | void) => Promise<void>;
    (name: string, callback: () => Promise<void> | void): void;
    (name: string, callback: (context: TestContext) => Promise<void> | void): void;
  };
  export const expect: (actual: unknown) => {
    toBe: (expected: unknown) => void;
    toContain: (expected: unknown) => void;
    toBeUndefined: () => void;
    toHaveText: (expected: string) => Promise<void>;
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

declare module "node:http" {
  export interface IncomingMessage {
    url?: string;
  }

  export interface ServerResponse {
    writeHead: (statusCode: number, headers?: Record<string, string>) => void;
    end: (chunk?: string) => void;
  }

  export interface AddressInfo {
    port: number;
  }

  export interface Server {
    listen: (port: number, hostname: string, callback: () => void) => void;
    address: () => AddressInfo | null;
    close: (callback: () => void) => void;
  }

  export function createServer(
    listener?: (req: IncomingMessage, res: ServerResponse) => void,
  ): Server;
}

declare const __dirname: string;
