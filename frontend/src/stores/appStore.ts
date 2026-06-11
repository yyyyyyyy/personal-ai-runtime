import { create } from "zustand";

export type Page =
  | "chat"
  | "goals"
  | "inbox"
  | "timeline"
  | "memories"
  | "trajectories"
  | "dashboard";

interface AppState {
  currentPage: Page;
  setPage: (page: Page) => void;
  experimentalTrajectoryEnabled: boolean;
  setExperimentalTrajectoryEnabled: (enabled: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentPage: "chat",
  setPage: (page) => set({ currentPage: page }),
  experimentalTrajectoryEnabled: false,
  setExperimentalTrajectoryEnabled: (enabled) =>
    set({ experimentalTrajectoryEnabled: enabled }),
}));
