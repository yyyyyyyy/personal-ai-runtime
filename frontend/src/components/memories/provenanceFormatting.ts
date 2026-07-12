import type { MemoryProvenanceEvent } from "../../api/client";

const EVENT_TYPE_LABELS: Record<string, string> = {
  MemoryDerived: "生成",
  MemoryUpdated: "更新",
  MemoryDecayed: "衰减",
  MemoryDeleted: "删除",
  MemoryRevoked: "撤销",
  MemoryIndexRepairFailed: "索引修复失败",
};

export function eventTypeLabel(t: string): string {
  return EVENT_TYPE_LABELS[t] || t;
}

export function eventDescription(e: MemoryProvenanceEvent): string {
  const p = e.payload as Record<string, unknown>;
  const conf = p.confidence;
  const content = typeof p.content === "string" ? p.content : "";
  switch (e.type) {
    case "MemoryDerived":
      return `由 ${e.actor} 抽取${typeof conf === "number" ? `，置信度 ${conf.toFixed(2)}` : ""}`;
    case "MemoryUpdated":
      if (content) {
        const snippet = content.length > 60 ? content.slice(0, 60) + "…" : content;
        return `内容由 ${e.actor} 更新为「${snippet}」`;
      }
      return `内容被 ${e.actor} 更新`;
    case "MemoryDecayed":
      return typeof conf === "number" ? `置信度衰减至 ${conf.toFixed(2)}` : "置信度衰减";
    case "MemoryDeleted":
      return `被 ${e.actor} 删除`;
    case "MemoryRevoked":
      return `被 ${e.actor} 撤销`;
    case "MemoryIndexRepairFailed": {
      const err = typeof p.error === "string" ? p.error : "";
      return err
        ? `向量索引修复失败：${err.length > 80 ? err.slice(0, 80) + "…" : err}`
        : "向量索引修复失败，记忆可能无法语义召回";
    }
    default:
      return `${e.actor}`;
  }
}
