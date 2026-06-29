/** Portrait API — AI user portrait page. */

import { API_BASE, request } from "./core";

export interface ProfileItem {
  data: Record<string, string>;
  confidence: number;
}

export interface HabitItem {
  id: string;
  content: string;
  confidence: number;
  source: string;
  origin: string;
  created_at?: string;
}

export interface GoalSummary {
  id: string;
  title: string;
  progress: number;
  importance: number;
  deadline: string | null;
  last_activity_at: string | null;
}

export interface PortraitData {
  profile: Record<string, ProfileItem | undefined>;
  habits: HabitItem[];
  goals: GoalSummary[];
}

export async function getPortrait(): Promise<PortraitData> {
  return request<PortraitData>(`${API_BASE}/memory/portrait`);
}
