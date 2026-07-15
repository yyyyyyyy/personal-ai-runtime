/** Barrel re-export of domain API modules.
 *  Prefer importing from domain modules (e.g. `../api/chat`).
 */

// Core
export {
  setAuthToken,
  getAuthToken,
  isAuthConfigured,
  authHeaders,
  request,
  requestFormData,
  ApiError,
} from "./core";

// Types
export type {
  HealthResponse,
  Conversation,
  Message,
  StreamEvent,
  SourceCitation,
  Notification,
  CostSummary,
  ModelCostItem,
  ToolSummaryItem,
  MemoryStats,
  HealthSnapshot,
  MemoryRow,
  MemoriesGrouped,
  SystemInfo,
  LlmProvidersResponse,
  InboxEmail,
  GoalAction,
  GoalEvent,
  Goal,
  WorkItemType,
  WorkItem,
  Approval,
  EnrichedApproval,
  DataSovereignty,
  DashboardData,
} from "./types";

// Chat
export {
  createConversation,
  listConversations,
  deleteConversation,
  updateConversation,
  getMessages,
  sendMessage,
} from "./chat";

// System
export {
  getSystemHealth,
  fetchSystemInfo,
  getLlmProviders,
  exportData,
  downloadExport,
  exportEncryptedData,
  importData,
  importEncryptedData,
  destroyAllData,
  getDashboard,
} from "./system";

// Goals
export {
  listGoals,
  getGoal,
  createGoal,
  updateGoal,
  deleteGoal,
  createGoalAction,
  updateGoalAction,
  decomposeGoal,
} from "./goals";

// Inbox
export { listInboxEmails, getInboxDigest, triggerInboxPoll, updateInboxEmailStatus } from "./inbox";

// Memory
export {
  listMemoriesGrouped,
  searchMemories,
  createMemory,
  deleteMemory,
  updateMemory,
  ratifyMemory,
  rejectMemory,
  contestMemory,
  getMemoryGraph,
  getMemoryProvenance,
} from "./memory";
export type {
  MemoryGraphNode,
  MemoryGraphEdge,
  MemoryGraph,
  MemoryProvenance,
  MemoryProvenanceEvent,
} from "./memory";

// Telemetry
export {
  getCostSummary,
  getCostByModel,
  getToolSummary,
  getMemoryStats,
  getHealth,
} from "./telemetry";

// Settings
export {
  getLlmSettings,
  updateLlmSettings,
  testLlmConnection,
  getEmailSettings,
  updateEmailSettings,
  testEmailConnection,
  getPromptConfig,
  updatePromptConfig,
  getCapabilityPolicy,
} from "./settings";
export type {
  LlmConfig,
  LlmProviderConfig,
  LlmSettingsResponse,
  EmailConfig,
  EmailSettingsResponse,
  LlmTestResult,
  EmailTestResult,
  PromptConfig,
  CapabilityPolicy,
} from "./settings";

// Approvals
export {
  listPendingApprovals,
  listEnrichedPendingApprovals,
  approveApproval,
  rejectApproval,
  resolveApproval,
} from "./approvals";

// Notifications
export { listNotifications, markNotificationRead, markAllNotificationsRead } from "./notifications";

// Knowledge
export {
  listKnowledgeDocuments,
  uploadKnowledgeDocument,
  deleteKnowledgeDocument,
  searchKnowledge,
} from "./knowledge";
export type { KnowledgeDocument, KnowledgeSearchResult } from "./knowledge";

// Timeline
export { listTimelineEvents } from "./timeline";
export type { TimelineEvent, TimelineResponse } from "./timeline";

// Connectors / MCP marketplace
export { listMcpRegistry, installMcpConnector } from "./connectors";
export type { McpRegistryServer } from "./connectors";
