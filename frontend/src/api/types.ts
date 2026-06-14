/** Shared types for the Personal AI Runtime API client. */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  auth_required: boolean;
  startup?: {
    status: string;
    warning_count: number;
    checks?: {
      mcp?: { total: number; connected: number; failed: number };
      llm?: { configured: boolean; model?: string };
      storage?: { data_dir_exists: boolean; data_dir_writable: boolean; sqlite_exists: boolean };
    };
  };
}

export interface Conversation {
  id: string;
  title: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  tool_calls: string | null;
  tool_call_id: string | null;
  created_at: string;
}

export interface StreamEvent {
  type: "text_delta" | "tool_call_start" | "tool_result" | "confirmation_required" | "done" | "error";
  content?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_call_id?: string;
  approval_id?: string;
  tool_calls?: Array<{
    index: number;
    id: string;
    function_name: string;
    arguments: string;
  }>;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  content: string;
  created_at: string;
  read?: number;
}

export interface CostSummary {
  total_calls: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cost: number;
  avg_latency_ms: number;
  failed_calls: number;
}

export interface ModelCostItem {
  provider: string;
  model: string;
  total_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost: number;
  avg_latency_ms: number;
  failed_calls: number;
}

export interface ToolSummaryItem {
  tool_name: string;
  total_calls: number;
  failed_calls: number;
  avg_latency_ms: number;
}

export interface MemoryStats {
  total_memories: number;
  categories: Record<string, number>;
  recent_7d: number;
}

export interface HealthSnapshot {
  task_queue_length: number;
  llm_failure_rate_24h: number;
  tool_failure_rate_24h: number;
}

export interface TimelineEvent {
  id: string;
  type: string;
  summary: string;
  timestamp: string;
  goal_id: string | null;
  payload: string | null;
}

export interface KeyInsightsParsed {
  surface?: string;
  insights?: string[];
  legacy?: boolean;
}

export interface Review {
  id: string;
  type: string;
  period_start: string;
  period_end: string;
  content: string;
  key_insights?: string;
  key_insights_parsed?: KeyInsightsParsed;
  created_at: string;
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  file_path?: string;
  chunk_count: number;
  created_at: string;
}

export interface MemoryRow {
  id: string;
  content: string;
  category?: string;
  origin?: string;
  claim_status?: string | null;
  confidence?: number;
  source?: string;
  created_at?: string;
}

export interface MemoriesGrouped {
  memories: MemoryRow[];
}

export interface SystemInfo {
  conversations: number;
  messages: number;
  goals: number;
  memories: number;
}

export interface LlmProvidersResponse {
  providers: Array<{ name: string; model?: string; available?: boolean }>;
  default: string;
}

export interface McpServerStatus {
  name: string;
  status: string;
  tool_count: number;
  reason?: string;
  startup_connect?: boolean;
}

export interface McpStatusResponse {
  enabled: boolean;
  servers: McpServerStatus[];
  total_tools: number;
}

export interface InboxEmail {
  id: string;
  sender: string;
  subject: string;
  preview: string;
  received_at: string;
  category: string;
  importance: number;
  reason: string;
  notified: number;
  digested: number;
  status?: "pending" | "read" | "handled";
  created_at: string;
}

export interface GoalAction {
  id: string;
  goal_id: string;
  title: string;
  status: string;
  created_at: string;
  completed_at: string | null;
}

export interface GoalEvent {
  id: string;
  type: string;
  summary: string;
  timestamp: string;
}

export interface Goal {
  id: string;
  title: string;
  description: string | null;
  status: string;
  progress: number;
  importance: number;
  urgency: number;
  deadline: string | null;
  parent_id: string | null;
  created_at: string;
  last_activity_at: string | null;
  actions?: GoalAction[];
  events?: GoalEvent[];
}

export interface Approval {
  id: string;
  action?: string;
  status: string;
  params?: string;
  created_at?: string;
}
