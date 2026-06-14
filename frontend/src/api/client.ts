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
  Notification,
  CostSummary,
  ModelCostItem,
  ToolSummaryItem,
  MemoryStats,
  HealthSnapshot,
  TimelineEvent,
  KeyInsightsParsed,
  Review,
  KnowledgeDocument,
  MemoryRow,
  MemoriesGrouped,
  SystemInfo,
  LlmProvidersResponse,
  McpServerStatus,
  McpStatusResponse,
  InboxEmail,
  GoalAction,
  GoalEvent,
  Goal,
  Approval,
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
  getMcpStatus,
  exportData,
  importData,
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
} from "./goals";

// Inbox
export { listInboxEmails, getInboxDigest, triggerInboxPoll, updateInboxEmailStatus } from "./inbox";

// Memory
export {
  listMemoriesGrouped,
  searchMemories,
  createMemory,
  deleteMemory,
} from "./memory";

// Knowledge
export {
  listKnowledgeDocuments,
  importKnowledgeDocument,
  uploadKnowledgeDocument,
  deleteKnowledgeDocument,
  searchKnowledge,
} from "./knowledge";

// Telemetry
export { getCostSummary, getCostByModel, getToolSummary, getMemoryStats, getHealth } from "./telemetry";

// Settings
export {
  getLlmSettings,
  updateLlmSettings,
  testLlmConnection,
  getEmailSettings,
  updateEmailSettings,
  testEmailConnection,
} from "./settings";
export type {
  LlmConfig,
  LlmProviderConfig,
  LlmSettingsResponse,
  EmailConfig,
  EmailSettingsResponse,
  LlmTestResult,
  EmailTestResult,
} from "./settings";

// Events
export { listEvents } from "./events";

// Reviews
export { listReviews, getReview, triggerMorningBrief } from "./reviews";

// Approvals
export { listPendingApprovals, resolveApproval } from "./approvals";

// Notifications
export {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
} from "./notifications";
