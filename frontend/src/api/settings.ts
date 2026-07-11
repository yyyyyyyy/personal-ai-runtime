/** Settings API — LLM and email configuration. */

import { API_BASE, request } from "./core";

export interface LlmProviderConfig {
  id: string;
  name: string;
  type: "openai_compatible" | "ollama";
  base_url: string;
  model: string;
  api_key: string;
  has_api_key?: boolean;
  enabled: boolean;
}

export interface LlmConfig {
  default_provider: string;
  temperature: number;
  max_tokens: number;
  providers: LlmProviderConfig[];
}

export interface LlmProviderStatus {
  name: string;
  model: string;
  type: string;
  is_default: boolean;
  available: boolean;
}

export interface LlmSettingsResponse {
  config: LlmConfig;
  default_model: string;
  providers_status: LlmProviderStatus[];
  presets: Record<string, { name: string; type: string; base_url: string; model: string }>;
  provider_types: Record<string, string>;
}

export interface EmailConfig {
  provider: string;
  user: string;
  password: string;
  imap_host: string;
  smtp_host: string;
  smtp_port: number;
  configured?: boolean;
}

export interface EmailSettingsResponse {
  config: EmailConfig;
  provider: string;
  help: string;
}

export interface LlmTestResult {
  ok: boolean;
  provider: string;
  model?: string;
  latency_ms?: number;
  error?: string;
}

export interface EmailTestResult {
  ok: boolean;
  imap_ok: boolean;
  smtp_ok: boolean;
  error?: string | null;
}

export async function getLlmSettings(): Promise<LlmSettingsResponse> {
  return request<LlmSettingsResponse>(`${API_BASE}/settings/llm`);
}

export async function updateLlmSettings(payload: Partial<LlmConfig>): Promise<LlmSettingsResponse> {
  return request<LlmSettingsResponse>(`${API_BASE}/settings/llm`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function testLlmConnection(providerId?: string): Promise<LlmTestResult> {
  return request<LlmTestResult>(`${API_BASE}/settings/llm/test`, {
    method: "POST",
    body: JSON.stringify(providerId ? { provider_id: providerId } : {}),
  });
}

export async function getEmailSettings(): Promise<EmailSettingsResponse> {
  return request<EmailSettingsResponse>(`${API_BASE}/settings/email`);
}

export async function updateEmailSettings(
  payload: Partial<EmailConfig>,
): Promise<{ config: EmailConfig }> {
  return request(`${API_BASE}/settings/email`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function testEmailConnection(
  payload?: Partial<
    Pick<EmailConfig, "user" | "password" | "imap_host" | "smtp_host" | "smtp_port">
  >,
): Promise<EmailTestResult> {
  return request<EmailTestResult>(`${API_BASE}/settings/email/test`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

// ── Prompt customization ──────────────────────────────────────────────────

export interface PromptConfig {
  identity: string;
  coding_rules: string;
  is_custom_identity: boolean;
  is_custom_coding_rules: boolean;
}

export async function getPromptConfig(): Promise<PromptConfig> {
  return request<PromptConfig>(`${API_BASE}/settings/prompt`);
}

export async function updatePromptConfig(payload: {
  identity?: string;
  coding_rules?: string;
}): Promise<{ ok: boolean }> {
  return request(`${API_BASE}/settings/prompt`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

// ── Capability policy (trust tiers) ───────────────────────────────────────

export interface CapabilityPolicy {
  auto_allow: string[];
  needs_user: string[];
  forbidden: string[];
  external_ingestion: string[];
}

export async function getCapabilityPolicy(): Promise<CapabilityPolicy> {
  return request<CapabilityPolicy>(`${API_BASE}/settings/capability-policy`);
}
