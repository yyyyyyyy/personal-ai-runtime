import { create } from "zustand";

export type Page = "chat" | "goals" | "timeline" | "dashboard";

interface AppState {
  currentPage: Page;
  setPage: (page: Page) => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentPage: "chat",
  setPage: (page) => set({ currentPage: page }),
}));
