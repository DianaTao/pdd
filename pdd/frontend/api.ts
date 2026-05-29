import YAML from 'yaml';
import type { PddrcConfig } from './types';

export const API_BASE_URL = import.meta.env.VITE_API_URL || '';
export const WS_BASE_URL = API_BASE_URL ? API_BASE_URL.replace('http', 'ws') : `ws://${window.location.host}`;

// ----------------------------------------------------------------------------
// Core server/command/file types
// ----------------------------------------------------------------------------
export interface ServerStatus {
  version: string;
  project_root: string;
  uptime_seconds: number;
  active_jobs: number;
  connected_clients: number;
}

export interface CommandInfo {
  name: string;
  description: string;
}

export interface JobHandle {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
}

export interface JobResult {
  job_id: string;
  status: string;
  result: any;
  error: string | null;
  cost: number;
  duration_seconds: number;
  completed_at: string | null;
}

export interface FileTreeNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileTreeNode[];
  size?: number;
  mtime?: string;
}

export interface FileContent {
  path: string;
  content: string;
  encoding: 'utf-8' | 'base64';
  size: number;
  is_binary: boolean;
  checksum?: string;
}

export interface PromptInfo {
  prompt: string;
  sync_basename: string;
  language?: string;
  context?: string;
  expected_outputs?: string[];
  code?: string;
  test?: string;
  example?: string;
}

export interface CommandRequest {
  command: string;
  args?: Record<string, any>;
  options?: Record<string, any>;
}

export interface RunResult {
  success: boolean;
  message: string;
  exit_code: number;
  stdout?: string | null;
  stderr?: string | null;
  error_details?: string | null;
}

export interface CancelResult {
  cancelled: boolean;
  message: string;
}

export interface CommandStatus {
  running: boolean;
  command: string | null;
}

export interface SpawnTerminalResponse {
  success: boolean;
  message: string;
  command: string;
  platform: string;
  job_id?: string;
}

export interface SpawnedJobStatus {
  job_id: string;
  command: string;
  status: 'running' | 'completed' | 'failed' | 'unknown';
  started_at: string;
  completed_at?: string;
  exit_code?: number;
}

// ----------------------------------------------------------------------------
// Prompt metrics/sync/model types
// ----------------------------------------------------------------------------
export interface CostEstimate {
  input_cost: number;
  model: string;
  tokens: number;
  cost_per_million: number;
  currency: string;
}

export interface TokenMetrics {
  token_count: number;
  context_limit: number;
  context_usage_percent: number;
  cost_estimate: CostEstimate | null;
}

export interface PromptAnalyzeRequest {
  path: string;
  model?: string;
  preprocess?: boolean;
  content?: string;
}

export interface PromptAnalyzeResponse {
  raw_content: string;
  processed_content: string | null;
  raw_metrics: TokenMetrics;
  processed_metrics: TokenMetrics | null;
  preprocessing_succeeded: boolean;
  preprocessing_error: string | null;
}

export type SyncStatusType = 'in_sync' | 'prompt_changed' | 'code_changed' | 'conflict' | 'never_synced';

export interface SyncStatus {
  status: SyncStatusType;
  last_sync_timestamp: string | null;
  last_sync_command: string | null;
  prompt_modified: boolean;
  code_modified: boolean;
  fingerprint_exists: boolean;
  prompt_exists: boolean;
  code_exists: boolean;
}

export interface ModelInfo {
  model: string;
  provider: string;
  input_cost: number;
  output_cost: number;
  elo: number;
  context_limit: number;
  max_thinking_tokens: number;
  reasoning_type: string;
  structured_output: boolean;
}

export interface ModelsResponse {
  models: ModelInfo[];
  default_model: string;
}

// ----------------------------------------------------------------------------
// Prompt-code diff analysis types
// ----------------------------------------------------------------------------
export interface PromptRange {
  startLine: number;
  endLine: number;
  text: string;
}

export interface CodeRange {
  startLine: number;
  endLine: number;
  text: string;
}

export interface DiffSection {
  id: string;
  promptRange: PromptRange;
  codeRanges: CodeRange[];
  status: 'matched' | 'partial' | 'missing' | 'extra';
  matchConfidence: number;
  semanticLabel: string;
  notes: string;
}

export interface LineMapping {
  promptLine: number;
  codeLines: number[];
  matchType: 'exact' | 'semantic' | 'partial' | 'none';
}

export interface HiddenKnowledge {
  type: 'magic_value' | 'algorithm_choice' | 'edge_case' | 'error_handling' | 'api_contract' | 'optimization' | 'business_logic' | 'assumption';
  location: { startLine: number; endLine: number };
  description: string;
  regenerationImpact: 'would_differ' | 'would_fail' | 'might_work';
  suggestedPromptAddition: string;
}

export interface DiffStats {
  totalRequirements: number;
  matchedRequirements: number;
  missingRequirements: number;
  totalCodeFeatures: number;
  documentedFeatures: number;
  undocumentedFeatures: number;
  promptToCodeCoverage: number;
  codeToPromptCoverage: number;
  hiddenKnowledgeCount: number;
  criticalGaps: number;
}

export interface DiffAnalysisResult {
  overallScore: number;
  canRegenerate: boolean;
  regenerationRisk: 'low' | 'medium' | 'high' | 'critical';
  promptToCodeScore: number;
  codeToPromptScore: number;
  summary: string;
  sections: DiffSection[];
  codeSections: DiffSection[];
  hiddenKnowledge: HiddenKnowledge[];
  lineMappings: LineMapping[];
  stats: DiffStats;
  missing: string[];
  extra: string[];
  suggestions: string[];
}

export interface DiffAnalysisRequest {
  prompt_content: string;
  code_content: string;
  strength?: number;
  mode?: 'quick' | 'detailed';
  include_tests?: boolean;
  prompt_path?: string;
  code_path?: string;
}

export interface DiffAnalysisResponse {
  result: DiffAnalysisResult;
  cost: number;
  model: string;
  analysisMode: string;
  cached: boolean;
  tests_included: boolean;
  test_files: string[];
}

// ----------------------------------------------------------------------------
// Prompt history/diff types
// ----------------------------------------------------------------------------
export interface PromptVersionInfo {
  commit_hash: string;
  commit_date: string;
  commit_message: string;
  author: string;
  prompt_content: string;
}

export interface PromptHistoryRequest {
  prompt_path: string;
  limit?: number;
}

export interface PromptHistoryResponse {
  versions: PromptVersionInfo[];
  current_content: string;
  has_uncommitted_changes: boolean;
}

export interface LinguisticChange {
  change_type: 'added' | 'removed' | 'modified';
  category: 'requirement' | 'constraint' | 'behavior' | 'format';
  description: string;
  old_text?: string;
  new_text?: string;
  impact: 'breaking' | 'enhancement' | 'clarification';
}

export interface PromptDiffRequest {
  prompt_path: string;
  version_a: string;
  version_b: string;
  code_path?: string;
  strength?: number;
}

export interface PromptDiffResponse {
  prompt_a_content: string;
  prompt_b_content: string;
  text_diff: string;
  linguistic_changes: LinguisticChange[];
  code_diff?: string;
  summary: string;
  cost: number;
  model: string;
  version_a_label: string;
  version_b_label: string;
  versions_swapped: boolean;
}

// ----------------------------------------------------------------------------
// Extracts cache types
// ----------------------------------------------------------------------------
export interface ExtractMetadata {
  cache_key: string;
  source_path: string;
  query: string;
  timestamp: string;
  source_hash: string;
  is_fresh: boolean | null;
}

export interface ExtractContent extends ExtractMetadata {
  content: string;
}

export interface ExtractListResponse {
  extracts: ExtractMetadata[];
  total: number;
  stale_count: number;
}

export interface PromptExtractInfo {
  include_path: string;
  query: string;
  cache_key: string;
  has_cached_entry: boolean;
  source_path?: string;
  timestamp?: string;
  is_fresh?: boolean | null;
}

// ----------------------------------------------------------------------------
// Architecture/auth/remote-generation types
// ----------------------------------------------------------------------------
export interface ArchitectureModule {
  reason: string;
  description: string;
  dependencies: string[];
  priority: number;
  filename: string;
  filepath: string;
  tags?: string[];
  interface?: { type: string; [key: string]: any };
  position?: { x: number; y: number };
  contract_summary?: any;
}

export interface ArchitectureCheckResult {
  exists: boolean;
  path?: string;
}

export interface ArchitectureValidationError {
  type: 'circular_dependency' | 'missing_dependency' | 'invalid_field';
  message: string;
  modules: string[];
}

export interface ArchitectureValidationWarning {
  type: 'duplicate_dependency' | 'orphan_module';
  message: string;
  modules: string[];
}

export interface ArchitectureValidationResult {
  valid: boolean;
  errors: ArchitectureValidationError[];
  warnings: ArchitectureValidationWarning[];
}

export interface ArchitectureSyncRequest {
  filenames?: string[] | null;
  dry_run?: boolean;
}

export interface ArchitectureSyncModuleResult {
  filename: string;
  success: boolean;
  updated: boolean;
  changes: {
    reason?: { old: string; new: string };
    interface?: { old: any; new: any };
    dependencies?: { old: string[]; new: string[] };
    contract_summary?: { old: any; new: any };
  };
  error?: string;
}

export interface ArchitectureSyncResult {
  success: boolean;
  updated_count: number;
  skipped_count: number;
  results: ArchitectureSyncModuleResult[];
  validation: ArchitectureValidationResult;
  errors: string[];
}

export interface GenerateTagsResult {
  success: boolean;
  tags: string | null;
  has_existing_tags: boolean;
  architecture_entry: Record<string, any> | null;
  error: string | null;
}

export interface AuthStatus {
  authenticated: boolean;
  cached: boolean;
  expires_at: number | null;
}

export interface LogoutResult {
  success: boolean;
  message: string;
}

export interface LoginResponse {
  success: boolean;
  user_code?: string;
  verification_uri?: string;
  expires_in?: number;
  poll_id?: string;
  error?: string;
}

export interface LoginPollResponse {
  status: 'pending' | 'completed' | 'expired' | 'error';
  message?: string;
}

export interface RemoteSessionInfo {
  sessionId: string;
  cloudUrl: string;
  projectName: string;
  projectPath: string;
  createdAt: string;
  lastHeartbeat: string;
  status: 'active' | 'stale';
  metadata: {
    hostname: string;
    platform: string;
    pythonVersion: string;
  };
}

export interface RemoteCommandRequest {
  sessionId: string;
  type: string;
  payload: {
    args?: Record<string, any>;
    options?: Record<string, any>;
  };
}

export interface RemoteCommandStatus {
  commandId: string;
  type: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  createdAt: string;
  updatedAt?: string;
  response?: {
    success?: boolean;
    message?: string;
    exit_code?: number;
    stdout?: string;
    stderr?: string;
    files_created?: string[];
    cost?: number;
    streaming?: boolean;
    error?: string;
  };
}

export interface GenerationGlobalOptions {
  strength?: number;
  temperature?: number;
  time?: number;
  verbose?: boolean;
  quiet?: boolean;
  force?: boolean;
  local?: boolean;
}

export interface GenerateArchitectureRequest {
  prdPath?: string;
  prdContent?: string;
  techStackPath?: string;
  techStackContent?: string;
  appName?: string;
  outputPath?: string;
  globalOptions?: GenerationGlobalOptions;
}

export interface GeneratePromptFromArchRequest {
  module: string;
  langOrFramework: string;
  architectureFile?: string;
  prdFile?: string;
  techStackFile?: string;
  outputPath?: string;
  globalOptions?: GenerationGlobalOptions;
}

export interface BatchGeneratePromptsRequest {
  modules: Array<{ module: string; langOrFramework: string }>;
  architectureFile?: string;
  prdFile?: string;
  techStackFile?: string;
  globalOptions?: GenerationGlobalOptions;
}

export interface PromptGenerationResult {
  module: string;
  success: boolean;
  error?: string;
}

// ----------------------------------------------------------------------------
// PDDApiClient implementation
// ----------------------------------------------------------------------------
class PDDApiClient {
  private baseUrl: string;
  private wsBaseUrl: string;
  private cachedCloudUrl: string | null = null;

  constructor() {
    this.baseUrl = API_BASE_URL;
    this.wsBaseUrl = WS_BASE_URL;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options?.headers,
    };

    const response = await fetch(url, { ...options, headers });

    if (!response.ok) {
      let detail = response.statusText;
      try {
        const errJson = await response.json();
        if (errJson.detail) detail = errJson.detail;
      } catch (e) {
        // Ignore JSON parse error
      }
      throw new Error(detail || `API Error: ${response.status}`);
    }

    return response.json();
  }

  // Local server endpoints
  async getStatus(): Promise<ServerStatus> {
    return this.request<ServerStatus>('/api/v1/status');
  }

  async getAuthStatus(): Promise<AuthStatus> {
    return this.request<AuthStatus>('/api/v1/auth/status');
  }

  async logout(): Promise<LogoutResult> {
    return this.request<LogoutResult>('/api/v1/auth/logout', { method: 'POST' });
  }

  async startLogin(options?: Record<string, any>): Promise<LoginResponse> {
    return this.request<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(options || {}),
    });
  }

  async pollLoginStatus(pollId: string): Promise<LoginPollResponse> {
    return this.request<LoginPollResponse>(`/api/v1/auth/login/poll/${encodeURIComponent(pollId)}`);
  }

  async getAvailableCommands(): Promise<CommandInfo[]> {
    return this.request<CommandInfo[]>('/api/v1/commands/available');
  }

  async executeCommand(request: CommandRequest): Promise<JobHandle> {
    return this.request<JobHandle>('/api/v1/commands/execute', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async runCommand(request: CommandRequest): Promise<RunResult> {
    return this.request<RunResult>('/api/v1/commands/run', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async cancelCommand(): Promise<CancelResult> {
    return this.request<CancelResult>('/api/v1/commands/cancel', { method: 'POST' });
  }

  async getCommandStatus(): Promise<CommandStatus> {
    return this.request<CommandStatus>('/api/v1/commands/status');
  }

  async getJobStatus(jobId: string): Promise<JobResult> {
    return this.request<JobResult>(`/api/v1/commands/jobs/${encodeURIComponent(jobId)}`);
  }

  async cancelJob(jobId: string): Promise<CancelResult> {
    return this.request<CancelResult>(`/api/v1/commands/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
  }

  async getJobHistory(limit = 50, offset = 0): Promise<JobResult[]> {
    return this.request<JobResult[]>(`/api/v1/commands/history?limit=${limit}&offset=${offset}`);
  }

  async spawnTerminal(request: CommandRequest): Promise<SpawnTerminalResponse> {
    return this.request<SpawnTerminalResponse>('/api/v1/commands/spawn-terminal', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getSpawnedJobStatus(jobId: string): Promise<SpawnedJobStatus> {
    return this.request<SpawnedJobStatus>(`/api/v1/commands/spawned-jobs/${encodeURIComponent(jobId)}/status`);
  }

  async getFileTree(path = '', depth = 3): Promise<FileTreeNode> {
    const params = new URLSearchParams();
    if (path) params.append('path', path);
    params.append('depth', depth.toString());
    return this.request<FileTreeNode>(`/api/v1/files/tree?${params.toString()}`);
  }

  async getFileContent(path: string): Promise<FileContent> {
    return this.request<FileContent>(`/api/v1/files/content?path=${encodeURIComponent(path)}`);
  }

  async writeFile(path: string, content: string, encoding: 'utf-8' | 'base64' = 'utf-8'): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>('/api/v1/files/write', {
      method: 'POST',
      body: JSON.stringify({ path, content, encoding }),
    });
  }

  async listPrompts(): Promise<PromptInfo[]> {
    return this.request<PromptInfo[]>('/api/v1/files/prompts');
  }

  async getChangedPrompts(baseBranch = 'main'): Promise<PromptInfo[]> {
    return this.request<PromptInfo[]>(`/api/v1/files/prompts/changed?base_branch=${encodeURIComponent(baseBranch)}`);
  }

  async analyzePrompt(request: PromptAnalyzeRequest): Promise<PromptAnalyzeResponse> {
    return this.request<PromptAnalyzeResponse>('/api/v1/prompts/analyze', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getSyncStatus(basename: string, language: string): Promise<SyncStatus> {
    const params = new URLSearchParams({ basename, language });
    return this.request<SyncStatus>(`/api/v1/prompts/sync-status?${params.toString()}`);
  }

  async getModels(): Promise<ModelsResponse> {
    return this.request<ModelsResponse>('/api/v1/prompts/models');
  }

  async analyzeDiff(request: DiffAnalysisRequest): Promise<DiffAnalysisResponse> {
    return this.request<DiffAnalysisResponse>('/api/v1/prompts/diff-analysis', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getPromptHistory(request: PromptHistoryRequest): Promise<PromptHistoryResponse> {
    return this.request<PromptHistoryResponse>('/api/v1/prompts/git-history', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getPromptDiff(request: PromptDiffRequest): Promise<PromptDiffResponse> {
    return this.request<PromptDiffResponse>('/api/v1/prompts/prompt-diff', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async validateArchitecture(modules: ArchitectureModule[]): Promise<ArchitectureValidationResult> {
    return this.request<ArchitectureValidationResult>('/api/v1/architecture/validate', {
      method: 'POST',
      body: JSON.stringify({ modules }),
    });
  }

  async syncArchitectureFromPrompts(request: ArchitectureSyncRequest = {}): Promise<ArchitectureSyncResult> {
    return this.request<ArchitectureSyncResult>('/api/v1/architecture/sync-from-prompts', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async generateTagsForPrompt(promptFilename: string): Promise<GenerateTagsResult> {
    return this.request<GenerateTagsResult>('/api/v1/architecture/generate-tags-for-prompt', {
      method: 'POST',
      body: JSON.stringify({ prompt_filename: promptFilename }),
    });
  }

  async rearrangeGraphLayout(architecturePath = 'architecture.json'): Promise<{ success: boolean; updated: boolean }> {
    return this.request<{ success: boolean; updated: boolean }>('/api/v1/architecture/rearrange', {
      method: 'POST',
      body: JSON.stringify({ architecture_path: architecturePath }),
    });
  }

  async generateArchitectureFromIssue(issueUrl: string, options: { verbose?: boolean; quiet?: boolean } = {}): Promise<JobHandle> {
    return this.request<JobHandle>('/api/v1/architecture/generate-from-issue', {
      method: 'POST',
      body: JSON.stringify({ issue_url: issueUrl, verbose: options.verbose ?? false, quiet: options.quiet ?? false }),
    });
  }

  async getJWTToken(): Promise<string | null> {
    try {
      const res = await this.request<{ jwt: string }>('/api/v1/auth/jwt-token');
      return res.jwt;
    } catch {
      return null;
    }
  }

  async fetchCloudUrl(): Promise<{ cloud_url: string }> {
    try {
      return await this.request<{ cloud_url: string }>('/api/v1/config/cloud-url');
    } catch (e) {
      console.warn('Failed to fetch cloud URL, falling back', e);
      return { cloud_url: import.meta.env.VITE_CLOUD_URL || 'https://us-central1-prompt-driven-development.cloudfunctions.net' };
    }
  }

  async listExtracts(checkFreshness = true): Promise<ExtractListResponse> {
    return this.request<ExtractListResponse>(`/api/v1/extracts?check_freshness=${checkFreshness}`);
  }

  async getExtract(cacheKey: string): Promise<ExtractContent> {
    return this.request<ExtractContent>(`/api/v1/extracts/${encodeURIComponent(cacheKey)}`);
  }

  async getExtractsForPrompt(promptPath: string): Promise<PromptExtractInfo[]> {
    return this.request<PromptExtractInfo[]>(`/api/v1/extracts/for-prompt?prompt_path=${encodeURIComponent(promptPath)}`);
  }

  // Config/analysis helpers
  async getPddrc(): Promise<PddrcConfig | null> {
    try {
      const content = await this.getFileContent('.pddrc');
      return YAML.parse(content.content) as PddrcConfig;
    } catch {
      return null;
    }
  }

  async savePddrc(config: PddrcConfig): Promise<void> {
    const yamlContent = YAML.stringify(config);
    await this.writeFile('.pddrc', yamlContent);
  }

  async analyzeFile(path: string, model?: string): Promise<TokenMetrics> {
    const res = await this.analyzePrompt({ path, model: model || 'claude-sonnet-4-20250514', preprocess: false });
    return res.raw_metrics;
  }

  // Architecture-file helpers
  async checkArchitectureExists(): Promise<ArchitectureCheckResult> {
    try {
      await this.getFileContent('architecture.json');
      return { exists: true, path: 'architecture.json' };
    } catch {
      return { exists: false };
    }
  }

  async getArchitecture(): Promise<ArchitectureModule[]> {
    const content = await this.getFileContent('architecture.json');
    return JSON.parse(content.content) as ArchitectureModule[];
  }

  async saveArchitecture(modules: ArchitectureModule[]): Promise<void> {
    await this.writeFile('architecture.json', JSON.stringify(modules, null, 2));
  }

  async listMarkdownFiles(): Promise<string[]> {
    const results: string[] = [];
    try {
      const tree = await this.getFileTree('', 4);
      const walk = (node: FileTreeNode) => {
        if (node.type === 'file' && node.name.endsWith('.md')) {
          results.push(node.path);
        }
        if (node.children) {
          node.children.forEach(walk);
        }
      };
      walk(tree);
    } catch (e) {
      console.error('Failed to list markdown files:', e);
    }
    return results;
  }

  // Generation workflow helpers
  async generateArchitecture(request: GenerateArchitectureRequest): Promise<RunResult> {
    const env: Record<string, string> = {};
    if (request.appName) env['APP_NAME'] = request.appName;
    
    if (request.prdContent) {
      await this.writeFile('.pdd/temp_prd.md', request.prdContent);
      env['PRD_FILE'] = '.pdd/temp_prd.md';
    } else if (request.prdPath) {
      env['PRD_FILE'] = request.prdPath;
    }
    
    if (request.techStackContent) {
      await this.writeFile('.pdd/temp_tech_stack.md', request.techStackContent);
      env['TECH_STACK_FILE'] = '.pdd/temp_tech_stack.md';
    } else if (request.techStackPath) {
      env['TECH_STACK_FILE'] = request.techStackPath;
    }

    const envArgs = Object.entries(env).map(([k, v]) => `${k}=${v}`);
    const options: Record<string, any> = {
      output: request.outputPath || 'architecture.json',
      template: 'architecture/architecture_json',
      env: envArgs
    };

    if (request.globalOptions) {
      if (request.globalOptions.strength !== undefined) options['strength'] = request.globalOptions.strength;
      if (request.globalOptions.temperature !== undefined) options['temperature'] = request.globalOptions.temperature;
      if (request.globalOptions.time !== undefined) options['time'] = request.globalOptions.time;
      if (request.globalOptions.verbose !== undefined) options['verbose'] = request.globalOptions.verbose;
      if (request.globalOptions.quiet !== undefined) options['quiet'] = request.globalOptions.quiet;
      if (request.globalOptions.force !== undefined) options['force'] = request.globalOptions.force;
    }

    return this.runCommand({ command: 'generate', args: {}, options });
  }

  async generatePddrcFromArchitecture(request: { architectureFile?: string; outputPath?: string; globalOptions?: GenerationGlobalOptions }): Promise<RunResult> {
    const envArgs = [`ARCHITECTURE_FILE=${request.architectureFile || 'architecture.json'}`];
    const options: Record<string, any> = {
      output: request.outputPath || '.pddrc',
      template: 'generic/generate_pddrc',
      env: envArgs
    };

    if (request.globalOptions) {
      if (request.globalOptions.strength !== undefined) options['strength'] = request.globalOptions.strength;
      if (request.globalOptions.temperature !== undefined) options['temperature'] = request.globalOptions.temperature;
      if (request.globalOptions.time !== undefined) options['time'] = request.globalOptions.time;
      if (request.globalOptions.verbose !== undefined) options['verbose'] = request.globalOptions.verbose;
      if (request.globalOptions.quiet !== undefined) options['quiet'] = request.globalOptions.quiet;
      if (request.globalOptions.force !== undefined) options['force'] = request.globalOptions.force;
    }

    return this.runCommand({ command: 'generate', args: {}, options });
  }

  async generatePromptFromArchitecture(request: GeneratePromptFromArchRequest): Promise<RunResult> {
    const envArgs = [
      `MODULE=${request.module}`,
      `LANG_OR_FRAMEWORK=${request.langOrFramework}`,
      `ARCHITECTURE_FILE=${request.architectureFile || 'architecture.json'}`
    ];
    if (request.prdFile) envArgs.push(`PRD_FILE=${request.prdFile}`);
    if (request.techStackFile) envArgs.push(`TECH_STACK_FILE=${request.techStackFile}`);

    const options: Record<string, any> = {
      output: request.outputPath || `prompts/${request.module}_${request.langOrFramework}.prompt`,
      template: 'generic/generate_prompt',
      env: envArgs
    };

    if (request.globalOptions) {
      if (request.globalOptions.strength !== undefined) options['strength'] = request.globalOptions.strength;
      if (request.globalOptions.temperature !== undefined) options['temperature'] = request.globalOptions.temperature;
      if (request.globalOptions.time !== undefined) options['time'] = request.globalOptions.time;
      if (request.globalOptions.verbose !== undefined) options['verbose'] = request.globalOptions.verbose;
      if (request.globalOptions.quiet !== undefined) options['quiet'] = request.globalOptions.quiet;
      if (request.globalOptions.force !== undefined) options['force'] = request.globalOptions.force;
    }

    return this.runCommand({ command: 'generate', args: {}, options });
  }

  async batchGeneratePrompts(
    request: BatchGeneratePromptsRequest,
    onProgress?: (current: number, total: number, moduleName: string) => void,
    shouldCancel?: () => boolean
  ): Promise<PromptGenerationResult[]> {
    const results: PromptGenerationResult[] = [];
    const total = request.modules.length;
    
    for (let i = 0; i < total; i++) {
      if (shouldCancel?.()) break;
      const mod = request.modules[i];
      onProgress?.(i + 1, total, mod.module);
      try {
        const res = await this.generatePromptFromArchitecture({
          module: mod.module,
          langOrFramework: mod.langOrFramework,
          architectureFile: request.architectureFile,
          prdFile: request.prdFile,
          techStackFile: request.techStackFile,
          globalOptions: request.globalOptions
        });
        results.push({ module: `${mod.module}_${mod.langOrFramework}`, success: res.success, error: res.success ? undefined : res.message });
      } catch (e: any) {
        results.push({ module: `${mod.module}_${mod.langOrFramework}`, success: false, error: e.message || String(e) });
      }
    }
    return results;
  }

  // Remote cloud session behavior
  async getCloudUrl(): Promise<string> {
    if (!this.cachedCloudUrl) {
      const { cloud_url } = await this.fetchCloudUrl();
      this.cachedCloudUrl = cloud_url;
    }
    return this.cachedCloudUrl;
  }

  async listRemoteSessions(): Promise<RemoteSessionInfo[]> {
    const token = await this.getJWTToken();
    if (!token) throw new Error('Not authenticated. Please run: pdd auth login');
    const cloudUrl = await this.getCloudUrl();
    const res = await fetch(`${cloudUrl}/listSessions`, { headers: { 'Authorization': `Bearer ${token}` } });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to list sessions: ${res.statusText}`);
    }
    const data = await res.json();
    return data.sessions || [];
  }

  async submitRemoteCommand(request: RemoteCommandRequest): Promise<{ commandId: string; status: string }> {
    const token = await this.getJWTToken();
    if (!token) throw new Error('Not authenticated. Please run: pdd auth login');
    const cloudUrl = await this.getCloudUrl();
    const res = await fetch(`${cloudUrl}/submitCommand`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to submit command: ${res.statusText}`);
    }
    return res.json();
  }

  async getRemoteCommandStatus(sessionId: string, commandId: string): Promise<RemoteCommandStatus | null> {
    const token = await this.getJWTToken();
    if (!token) throw new Error('Not authenticated. Please run: pdd auth login');
    const cloudUrl = await this.getCloudUrl();
    const res = await fetch(`${cloudUrl}/getCommandStatus?sessionId=${encodeURIComponent(sessionId)}&commandId=${encodeURIComponent(commandId)}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.status === 404) return null;
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to get command status: ${res.statusText}`);
    }
    const data = await res.json();
    return data.command || null;
  }

  async cancelRemoteCommand(sessionId: string, commandId: string): Promise<{ success: boolean; message: string }> {
    const token = await this.getJWTToken();
    if (!token) throw new Error('Not authenticated. Please run: pdd auth login');
    const cloudUrl = await this.getCloudUrl();
    const res = await fetch(`${cloudUrl}/cancelCommand`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId, commandId })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Failed to cancel command: ${res.statusText}`);
    }
    return res.json();
  }

  // Job stream WebSocket helpers
  connectToJobStream(
    jobId: string,
    callbacks: {
      onMessage?: (type: string, data: any) => void;
      onStdout?: (text: string) => void;
      onStderr?: (text: string) => void;
      onProgress?: (current: number, total: number, message: string) => void;
      onComplete?: (success: boolean, result: any, cost: number) => void;
      onError?: (error: Error) => void;
      onClose?: () => void;
    }
  ): WebSocket {
    const ws = new WebSocket(`${this.wsBaseUrl}/ws/jobs/${encodeURIComponent(jobId)}/stream`);
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        callbacks.onMessage?.(message.type, message.data);
        switch (message.type) {
          case 'stdout': callbacks.onStdout?.(message.data); break;
          case 'stderr': callbacks.onStderr?.(message.data); break;
          case 'progress': callbacks.onProgress?.(message.current, message.total, message.message); break;
          case 'complete': callbacks.onComplete?.(message.data?.success, message.data?.result, message.data?.cost || 0); break;
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };
    
    ws.onerror = () => callbacks.onError?.(new Error('WebSocket error'));
    ws.onclose = () => callbacks.onClose?.();
    
    return ws;
  }

  sendCancelRequest(ws: WebSocket): void {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'cancel' }));
    }
  }
}

export const api = new PDDApiClient();
export { PDDApiClient };