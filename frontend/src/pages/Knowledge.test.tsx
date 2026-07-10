import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithRouter } from "../test-utils";
import KnowledgePage from "./Knowledge";

vi.mock("../api/core", () => ({
  API_BASE: "/api",
  request: vi.fn(),
}));

import { request } from "../api/core";

const mockRequest = vi.mocked(request);

const sampleDoc = {
  id: "doc-1",
  filename: "架构设计.md",
  size: 2048,
  chunks: 3,
  uploaded_at: "2026-06-28T10:00:00Z",
};

describe("KnowledgePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRequest.mockResolvedValue({ documents: [] });
  });

  it("shows loading then empty state", async () => {
    renderWithRouter(<KnowledgePage />);
    await waitFor(() => {
      expect(screen.getByText("还没有上传任何文档")).toBeInTheDocument();
    });
  });

  it("renders document list", async () => {
    mockRequest.mockResolvedValue({ documents: [sampleDoc] });
    renderWithRouter(<KnowledgePage />);
    await waitFor(() => {
      expect(screen.getByText("架构设计.md")).toBeInTheDocument();
      expect(screen.getByText("已上传文档 (1)")).toBeInTheDocument();
    });
  });

  it("shows error when fetch fails", async () => {
    mockRequest.mockRejectedValue(new Error("网络错误"));
    renderWithRouter(<KnowledgePage />);
    await waitFor(() => {
      expect(screen.getByText("网络错误")).toBeInTheDocument();
    });
  });

  it("deletes document on trash click", async () => {
    mockRequest.mockResolvedValueOnce({ documents: [sampleDoc] }).mockResolvedValueOnce(undefined);
    renderWithRouter(<KnowledgePage />);
    await waitFor(() => expect(screen.getByText("架构设计.md")).toBeInTheDocument());
    fireEvent.click(screen.getByTitle("删除文档"));
    await waitFor(() => {
      expect(mockRequest).toHaveBeenCalledWith("/api/knowledge/documents/doc-1", {
        method: "DELETE",
      });
      expect(screen.getByText("还没有上传任何文档")).toBeInTheDocument();
    });
  });

  it("searches knowledge base", async () => {
    mockRequest.mockResolvedValueOnce({ documents: [] }).mockResolvedValueOnce({
      results: [
        {
          id: "r1",
          content: "Rust 所有权模型",
          metadata: { source_file: "rust.md" },
          distance: 0.12,
        },
      ],
    });
    renderWithRouter(<KnowledgePage />);
    await waitFor(() => expect(screen.getByPlaceholderText("在知识库中搜索…")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("在知识库中搜索…"), {
      target: { value: "Rust" },
    });
    fireEvent.click(screen.getByText("搜索"));
    await waitFor(() => {
      expect(screen.getByText("Rust 所有权模型")).toBeInTheDocument();
      expect(screen.getByText("搜索结果 (1)")).toBeInTheDocument();
    });
  });

  it("uploads file via fetch", async () => {
    mockRequest.mockResolvedValue({ documents: [] });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithRouter(<KnowledgePage />);
    await waitFor(() => expect(screen.getByText("选择文件")).toBeInTheDocument());

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "notes.md", { type: "text/markdown" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/knowledge/upload",
        expect.objectContaining({ method: "POST" }),
      );
    });
    vi.unstubAllGlobals();
  });
});
