import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithRouter, MockApiError } from "../../test-utils";
import OnboardingWizard from "./OnboardingWizard";

const mockNavigate = vi.fn();
const addConversation = vi.fn();
const setActiveConversation = vi.fn();
const setPendingPrompt = vi.fn();
const { addError } = vi.hoisted(() => ({
  addError: vi.fn(),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("../../api/client", () => ({
  getSystemHealth: vi.fn(),
  getLlmProviders: vi.fn(),
  createConversation: vi.fn(),
  ApiError: MockApiError,
}));

vi.mock("../../stores/chatStore", () => ({
  useChatStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ addConversation, setActiveConversation, setPendingPrompt }),
}));

vi.mock("../../stores/errorStore", () => ({
  useErrorStore: (selector: (s: { addError: ReturnType<typeof vi.fn> }) => unknown) =>
    selector({ addError }),
}));

import { getSystemHealth, getLlmProviders, createConversation } from "../../api/client";

const mockHealth = vi.mocked(getSystemHealth);
const mockLlm = vi.mocked(getLlmProviders);
const mockCreateConv = vi.mocked(createConversation);

describe("OnboardingWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("shows step 1 initially", () => {
    renderWithRouter(<OnboardingWizard onComplete={vi.fn()} />);
    expect(screen.getByText("连接后端")).toBeInTheDocument();
    expect(screen.getByText("首次引导 1/3")).toBeInTheDocument();
  });

  it("advances to step 2 after health check", async () => {
    mockHealth.mockResolvedValue({
      status: "ok",
      auth_required: false,
      startup: { checks: { llm: { configured: false } } },
    } as Awaited<ReturnType<typeof getSystemHealth>>);
    renderWithRouter(<OnboardingWizard onComplete={vi.fn()} />);
    fireEvent.click(screen.getByText("运行检查"));
    await waitFor(() => expect(screen.getByText("后端运行正常")).toBeInTheDocument());
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => {
      expect(screen.getByText("配置 AI 大脑")).toBeInTheDocument();
    });
  });

  it("skips to step 3 when LLM already configured", async () => {
    mockHealth.mockResolvedValue({
      status: "ok",
      auth_required: false,
      startup: { checks: { llm: { configured: true } } },
    } as Awaited<ReturnType<typeof getSystemHealth>>);
    renderWithRouter(<OnboardingWizard onComplete={vi.fn()} />);
    fireEvent.click(screen.getByText("运行检查"));
    await waitFor(() => expect(screen.getByText("后端运行正常")).toBeInTheDocument());
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => {
      expect(screen.getByText("开始第一次对话")).toBeInTheDocument();
    });
  });

  it("shows error when health check fails", async () => {
    mockHealth.mockRejectedValue(new MockApiError("无法连接", 503));
    renderWithRouter(<OnboardingWizard onComplete={vi.fn()} />);
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => {
      expect(screen.getByText("无法连接")).toBeInTheDocument();
      expect(screen.getByText("连接后端")).toBeInTheDocument();
    });
  });

  it("shows settings button when LLM check fails", async () => {
    mockHealth.mockResolvedValue({
      status: "ok",
      auth_required: false,
      startup: { checks: { llm: { configured: false } } },
    } as Awaited<ReturnType<typeof getSystemHealth>>);
    mockLlm.mockResolvedValue({ providers: [], default: "" });
    renderWithRouter(<OnboardingWizard onComplete={vi.fn()} />);
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("配置 AI 大脑")).toBeInTheDocument());
    fireEvent.click(screen.getByText("运行检查"));
    await waitFor(() => {
      expect(screen.getByText("前往设置页面配置")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("前往设置页面配置"));
    expect(localStorage.getItem("onboarding_done")).toBe("1");
    expect(mockNavigate).toHaveBeenCalledWith("/settings");
  });

  it("launches conversation from starter prompt", async () => {
    mockHealth.mockResolvedValue({
      status: "ok",
      auth_required: false,
      startup: { checks: { llm: { configured: true } } },
    } as Awaited<ReturnType<typeof getSystemHealth>>);
    mockCreateConv.mockResolvedValue({
      id: "conv-new",
      title: "目标规划",
      summary: null,
      created_at: "2026-06-28T10:00:00Z",
      updated_at: "2026-06-28T10:00:00Z",
    });
    const onComplete = vi.fn();
    renderWithRouter(<OnboardingWizard onComplete={onComplete} />);
    fireEvent.click(screen.getByText("运行检查"));
    await waitFor(() => expect(screen.getByText("后端运行正常")).toBeInTheDocument());
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("帮我规划一个目标")).toBeInTheDocument());
    fireEvent.click(screen.getByText("帮我规划一个目标"));
    await waitFor(() => {
      expect(mockCreateConv).toHaveBeenCalledWith("目标规划");
      expect(setPendingPrompt).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith("/chat/conv-new");
      expect(onComplete).toHaveBeenCalled();
    });
  });

  it("calls addError when createConversation fails", async () => {
    mockHealth.mockResolvedValue({
      status: "ok",
      auth_required: false,
      startup: { checks: { llm: { configured: true } } },
    } as Awaited<ReturnType<typeof getSystemHealth>>);
    mockCreateConv.mockRejectedValue(new MockApiError("创建失败", 500));
    renderWithRouter(<OnboardingWizard onComplete={vi.fn()} />);
    fireEvent.click(screen.getByText("运行检查"));
    await waitFor(() => expect(screen.getByText("后端运行正常")).toBeInTheDocument());
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("自由聊几句")).toBeInTheDocument());
    fireEvent.click(screen.getByText("自由聊几句"));
    await waitFor(() => {
      expect(addError).toHaveBeenCalledWith("创建失败", "对话");
    });
  });

  it("skip sets onboarding_done and calls onComplete", () => {
    const onComplete = vi.fn();
    renderWithRouter(<OnboardingWizard onComplete={onComplete} />);
    fireEvent.click(screen.getByText("跳过"));
    expect(localStorage.getItem("onboarding_done")).toBe("1");
    expect(onComplete).toHaveBeenCalledOnce();
  });
});
