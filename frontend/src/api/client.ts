/** Barrel re-export for backward compatibility.
 *  New code should import directly from domain modules (e.g. `../api/chat`).
 */

// Core
export { setAuthToken, getAuthToken, isAuthConfigured, request, ApiError } from "./core";

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
} from "./memory";
export type { MemoryGraphNode, MemoryGraphEdge, MemoryGraph } from "./memory";

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
