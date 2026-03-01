declare namespace JSX {
  interface Element {}
  interface IntrinsicElements {
    [elemName: string]: unknown;
  }
}

declare module "react" {
  export type ReactNode = unknown;

  export function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  export function useMemo<T>(factory: () => T, deps: readonly unknown[]): T;
  export function useState<T>(
    initialState: T | (() => T),
  ): [T, (value: T | ((previous: T) => T)) => void];
}

declare module "react/jsx-runtime" {
  export function jsx(type: unknown, props: unknown, key?: string): JSX.Element;
  export function jsxs(type: unknown, props: unknown, key?: string): JSX.Element;
  export const Fragment: unknown;
}
