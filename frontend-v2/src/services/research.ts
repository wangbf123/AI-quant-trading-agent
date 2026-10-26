/** Incremental research API for the retained QuantaAlpha workbench. */
export type ResearchRecord = Record<string, unknown>;

export interface ResearchMetrics {
  [key: string]: number | null | undefined;
}

export interface ResearchTrial {
  id: string;
  index?: number;
  strategy?: ResearchRecord;
  config?: ResearchRecord;
  metrics?: ResearchMetrics;
  failure_tags?: string[];
  reasoning?: string;
  status?: string;
  error?: string;
}

export interface ResearchMemory {
  id?: string;
  category?: string;
  description?: string;
  evidence?: unknown;
  strategy_family?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface ResearchEvent {
  timestamp?: string;
  kind?: string;
  step?: number | string;
  message?: string;
  details?: unknown;
}

export interface ResearchEvaluation {
  metrics?: ResearchMetrics;
  equity?: ResearchRecord[];
  curve?: ResearchRecord[];
  diagnostics?: ResearchRecord;
}

export interface ResearchResult {
  trials?: ResearchTrial[];
  memories?: ResearchMemory[];
  validation?: ResearchEvaluation | null;
  best_candidate?: ResearchRecord | string | null;
  holdout?: ResearchEvaluation | null;
  ablation?: ResearchRecord | null;
  events?: ResearchEvent[];
  provenance?: ResearchRecord;
  [key: string]: unknown;
}

export interface ResearchTask {
  id: string;
  status: string;
  events?: ResearchEvent[];
  error?: string | null;
  result?: ResearchResult | null;
}

export interface ResearchProtocol {
  id: string;
  name?: string;
  state: string;
  created_at?: string;
  updated_at?: string;
  protocol: ResearchRecord;
  task?: ResearchTask | null;
  result?: ResearchResult | null;
  frozen_candidate?: ResearchRecord | null;
}

export interface ResearchOverview {
  protocols: ResearchProtocol[];
  memories: ResearchMemory[];
  capabilities: Record<string, boolean | string | null>;
}

export interface ResearchRunConfig {
  budget: number;
  seed: number;
  use_memory: boolean;
  run_ablation: boolean;
  planner?: 'demo' | 'llm';
  objective?: string;
}

const BASE = '/api/v1/research';

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.success === false) {
    const detail = payload?.detail ?? payload?.error ?? payload?.message;
    throw new Error(typeof detail === 'string' ? detail : `请求失败 (${response.status})`);
  }
  return (payload?.data ?? payload) as T;
}

export const getResearchOverview = () => request<ResearchOverview>('/overview');
export const getResearchProtocol = (id: string) =>
  request<{ protocol: ResearchProtocol }>(`/protocols/${encodeURIComponent(id)}`).then(data => data.protocol);
export const createResearchProtocol = (config: ResearchRecord) =>
  request<{ protocol: ResearchProtocol }>('/protocols', config);
export const createResearchDemo = (config: ResearchRunConfig) =>
  request<{ protocol: ResearchProtocol; task: ResearchTask }>('/demo', config);
export const runResearchProtocol = (id: string, config: ResearchRunConfig) =>
  request<{ protocol?: ResearchProtocol; task: ResearchTask }>(`/protocols/${encodeURIComponent(id)}/run`, config);
export const freezeResearchCandidate = (id: string, candidateId: string) =>
  request<{ protocol: ResearchProtocol }>(`/protocols/${encodeURIComponent(id)}/freeze`, { candidate_id: candidateId });
export const finalizeResearchProtocol = (id: string) =>
  request<{ protocol?: ResearchProtocol; task?: ResearchTask }>(`/protocols/${encodeURIComponent(id)}/finalize`, {});

export async function exportResearchProtocol(id: string, format: 'json' | 'markdown' = 'json'): Promise<void> {
  const response = await fetch(`${BASE}/protocols/${encodeURIComponent(id)}/${format === 'markdown' ? 'report' : 'export'}`);
  if (!response.ok) throw new Error(`导出失败 (${response.status})`);
  const content = format === 'markdown' ? await response.text() : JSON.stringify(await response.json(), null, 2);
  const url = URL.createObjectURL(new Blob([content], { type: format === 'markdown' ? 'text/markdown' : 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `research-${id}.${format === 'markdown' ? 'md' : 'json'}`;
  anchor.click();
  URL.revokeObjectURL(url);
}
