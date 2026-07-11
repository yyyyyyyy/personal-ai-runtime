/**
 * Settings page queries — LLM/email core config, health, capability policy,
 * prompt editor, and MCP registry.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getLlmSettings,
  getEmailSettings,
  getSystemHealth,
  getPromptConfig,
  getCapabilityPolicy,
  type LlmSettingsResponse,
  type EmailSettingsResponse,
  type HealthResponse,
  type PromptConfig,
  type CapabilityPolicy,
} from "../api/client";
import { listMcpRegistry } from "../api/connectors";
import { queryKeys } from "./useWsInvalidationBridge";

export function useSettingsCoreQuery() {
  return useQuery<{ llm: LlmSettingsResponse; email: EmailSettingsResponse }>({
    queryKey: queryKeys.settingsCore,
    queryFn: async () => {
      const [llm, email] = await Promise.all([getLlmSettings(), getEmailSettings()]);
      return { llm, email };
    },
    staleTime: 30_000,
  });
}

export function useSettingsHealthQuery() {
  return useQuery<HealthResponse>({
    queryKey: queryKeys.settingsHealth,
    queryFn: getSystemHealth,
    staleTime: 30_000,
    retry: 1,
  });
}

export function useCapabilityPolicyQuery() {
  return useQuery<CapabilityPolicy>({
    queryKey: queryKeys.capabilityPolicy,
    queryFn: getCapabilityPolicy,
    staleTime: 60_000,
  });
}

export function usePromptConfigQuery() {
  return useQuery<PromptConfig>({
    queryKey: queryKeys.promptConfig,
    queryFn: getPromptConfig,
    staleTime: 30_000,
  });
}

export function useMcpRegistryQuery() {
  return useQuery({
    queryKey: queryKeys.mcpRegistry,
    queryFn: listMcpRegistry,
    staleTime: 60_000,
  });
}

export function useInvalidateSettings() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: queryKeys.settingsCore });
    void qc.invalidateQueries({ queryKey: queryKeys.settingsHealth });
  };
}
