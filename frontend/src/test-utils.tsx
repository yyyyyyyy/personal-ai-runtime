import { render, type RenderOptions } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";

interface RenderWithRouterOptions extends Omit<RenderOptions, "wrapper"> {
  initialEntries?: string[];
}

/** Render a component wrapped in MemoryRouter (default entry "/"). */
export function renderWithRouter(
  ui: ReactElement,
  { initialEntries = ["/"], ...options }: RenderWithRouterOptions = {},
) {
  return render(<MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>, options);
}

/** Zustand selector mock for use in vi.mock factories. */
export function createZustandMock<T extends Record<string, unknown>>(state: T) {
  return (selector: (s: T) => unknown) => selector(state);
}

/** ApiError class matching api/core for vi.mock factories. */
export class MockApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
