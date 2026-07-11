import { useRef, useState } from "react";
import { ApiError } from "../api/core";
import {
  uploadKnowledgeDocument,
  deleteKnowledgeDocument,
  searchKnowledge,
  type KnowledgeSearchResult,
} from "../api/knowledge";
import { useKnowledgeDocumentsQuery, useInvalidateKnowledge } from "../hooks/useKnowledgeQuery";
import { FileText, Upload, Trash2, Search, Loader2, BookOpen } from "lucide-react";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function errMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError || err instanceof Error) return err.message;
  return fallback;
}

export default function KnowledgePage() {
  const { data: documents = [], isLoading: loading, error: loadError } = useKnowledgeDocumentsQuery();
  const invalidateKnowledge = useInvalidateKnowledge();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const displayError = error || (loadError ? errMessage(loadError, "加载失败") : "");

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError("");
    try {
      await uploadKnowledgeDocument(file);
      invalidateKnowledge();
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setError(errMessage(err, "上传失败"));
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteKnowledgeDocument(id);
      invalidateKnowledge();
    } catch (e) {
      setError(errMessage(e, "删除失败"));
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setError("");
    try {
      const results = await searchKnowledge(searchQuery, 5);
      setSearchResults(results);
    } catch (e) {
      setError(errMessage(e, "搜索失败"));
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-200">知识库</h2>
            <p className="text-sm text-gray-500 mt-0.5">上传文档，让 AI 搜索你的知识</p>
          </div>
        </div>

        {displayError && (
          <div className="bg-red-900/20 border border-red-700/50 rounded-lg p-3 mb-4 text-sm text-red-400">
            {displayError}
            <button onClick={() => setError("")} className="ml-2 text-xs underline">
              关闭
            </button>
          </div>
        )}

        {/* Upload zone */}
        <div className="bg-gray-900 border border-gray-800 border-dashed rounded-xl p-8 mb-6 text-center">
          <Upload size={32} className="mx-auto mb-3 text-gray-600" />
          <p className="text-sm text-gray-400 mb-3">拖拽文件到此处，或点击上传</p>
          <p className="text-xs text-gray-600 mb-4">
            支持 PDF / Markdown / TXT / JSON / CSV（最大 10 MB）
          </p>
          <label className="inline-block">
            <span className="inline-flex px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-medium cursor-pointer transition-colors">
              {uploading ? (
                <>
                  <Loader2 size={14} className="animate-spin mr-2" />
                  上传中…
                </>
              ) : (
                "选择文件"
              )}
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.md,.txt,.markdown,.json,.csv"
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>

        {/* Search */}
        <div className="flex gap-2 mb-6">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="在知识库中搜索…"
              className="w-full bg-gray-900 border border-gray-800 rounded-lg pl-9 pr-4 py-2 text-sm text-gray-300 placeholder-gray-600 focus:border-emerald-500 focus:outline-none"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors disabled:opacity-50"
          >
            {searching ? <Loader2 size={14} className="animate-spin" /> : "搜索"}
          </button>
        </div>

        {/* Search results */}
        {searchResults.length > 0 && (
          <div className="mb-6">
            <h3 className="text-sm font-medium text-gray-400 mb-3">
              搜索结果 ({searchResults.length})
            </h3>
            <div className="space-y-2">
              {searchResults.map((r) => (
                <div key={r.id} className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                  <div className="text-sm text-gray-300 mb-1">
                    {r.content.length > 200 ? r.content.substring(0, 200) + "…" : r.content}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-gray-600">
                    <span>
                      {r.metadata?.source_file ? String(r.metadata.source_file) : "未知文件"}
                    </span>
                    <span>·</span>
                    <span>相关度: {(r.distance * 100).toFixed(1)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Document list */}
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 size={20} className="text-gray-400 animate-spin" />
          </div>
        ) : documents.length === 0 ? (
          <div className="text-center py-8">
            <BookOpen size={32} className="mx-auto mb-3 text-gray-700" />
            <p className="text-gray-500 text-sm">还没有上传任何文档</p>
          </div>
        ) : (
          <div>
            <h3 className="text-sm font-medium text-gray-400 mb-3">
              已上传文档 ({documents.length})
            </h3>
            <div className="space-y-2">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-lg p-3 group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <FileText size={18} className="text-gray-500 shrink-0" />
                    <div className="min-w-0">
                      <div className="text-sm text-gray-300 truncate">{doc.filename}</div>
                      <div className="text-xs text-gray-600">
                        {formatSize(doc.size)} · {doc.chunks} 个分块 ·{" "}
                        {doc.uploaded_at
                          ? new Date(doc.uploaded_at).toLocaleDateString("zh-CN")
                          : ""}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all shrink-0 ml-3"
                    title="删除文档"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
