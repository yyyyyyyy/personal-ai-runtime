import { lazy } from "react";
import { createBrowserRouter } from "react-router-dom";
import Layout from "./Layout";

const ChatPage = lazy(() => import("./pages/ChatPage"));
const GoalsPage = lazy(() => import("./pages/Goals"));
const InboxPage = lazy(() => import("./pages/Inbox"));
const MemoriesPage = lazy(() => import("./pages/Memories"));
const DashboardPage = lazy(() => import("./pages/Dashboard"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const ApprovalsPage = lazy(() => import("./pages/Approvals"));
const TimelinePage = lazy(() => import("./pages/Timeline"));
const KnowledgePage = lazy(() => import("./pages/Knowledge"));
const WorkflowListPage = lazy(() => import("./pages/WorkflowList"));
const WorkflowEditorPage = lazy(() => import("./pages/WorkflowEditor"));

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <ChatPage /> },
      { path: "chat/:conversationId", element: <ChatPage /> },
      { path: "goals", element: <GoalsPage /> },
      { path: "goals/:goalId", element: <GoalsPage /> },
      { path: "inbox", element: <InboxPage /> },
      { path: "memories", element: <MemoriesPage /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "approvals", element: <ApprovalsPage /> },
      { path: "timeline", element: <TimelinePage /> },
      { path: "knowledge", element: <KnowledgePage /> },
      { path: "workflows", element: <WorkflowListPage /> },
      { path: "workflows/:workflowId", element: <WorkflowEditorPage /> },
    ],
  },
]);
