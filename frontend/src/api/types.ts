/** Shared types for the Personal AI Runtime API client. */

export interface HealthResponse {
  status: string;
  service: string;
  version?: string;
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
  sources?: string | null;
  created_at: string;
}

/** Citation source reference */
export interface SourceCitation {
  id: string;
  type: "memory" | "email" | "goal" | "document";
  title: string;
}

export interface StreamEvent {
  type:
    | "text_delta"
    | "tool_call_start"
    | "tool_result"
    | "confirmation_required"
    | "done"
    | "error"
    | "sources"
    | "ping";
  content?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_call_id?: string;
  approval_id?: string;
  sources?: SourceCitation[];
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
  memory_index_repairs_pending?: number;
  memory_index_repairs_failed_permanent?: number;
}

export interface MemoryRow {
  id: string;
  content: string;
  category?: string;
  origin?: string;
  claim_status?: string | null;
  confidence?: number;
  source?: string;
  source_document_id?: string | null;
  source_document_name?: string | null;
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
  event_log: number;
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

/**
 * Goal — view-model over WorkItem (work_type=goal) plus optional embedded
 * actions/events. UI consumers use this shape; API clients convert at the edge.
 */
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

/**
 * WorkItem — unified type for tasks, actions, goals.
 * Goal/GoalAction remain thin view-model adapters used by the Goals page.
 */
export type WorkItemType = "task" | "action" | "background" | "goal";

export interface WorkItem {
  id: string;
  title: string;
  description: string | null;
  work_type: WorkItemType;
  parent_work_id: string | null;
  parent_goal_id: string | null;
  status: string;
  priority: number;
  dependencies_json: string | null;
  executable_plan: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  // v1.0 goal-unification fields (populated when work_type="goal")
  progress: number;
  importance: number;
  urgency: number;
  deadline: string | null;
  last_activity_at: string | null;
}

export interface Approval {
  id: string;
  action?: string;
  status: string;
  params?: string;
  created_at?: string;
}

export interface EnrichedApproval extends Approval {
  /** 流程类型：对话 | 任务 | 定时任务 | 测试 | 系统 | 未知 */
  flow_type: string;
  /** 流程标识：对话标题、任务名称、correlation_id 等 */
  flow_label: string;
  /** 事件关联标识 */
  correlation_id: string;
  /** 发起者 */
  proposed_by?: string;
  /** 关联任务ID */
  task_id?: string | null;
  /** 过期时间 */
  expires_at?: string;
  /** 审批解决时间 */
  resolved_at?: string | null;
  /** 审批人 */
  resolved_by?: string | null;
}

/** Dashboard data sovereignty panel */
export interface DataSovereignty {
  total_events: number;
  total_memories: number;
  memories_self_report: number;
  memories_claim: number;
  total_goals: number;
  goals_active: number;
  goals_completed: number;
  total_conversations: number;
  total_messages: number;
  data_location: string;
  last_belief_reflection: string | null;
  export_supported: boolean;
}

export interface DashboardData {
  generated_at: string;
  data_sovereignty: DataSovereignty;
  active_goals: {
    count: number;
    top: Array<{
      id: string;
      title: string;
      progress: number;
      importance: number;
    }>;
  };
}
