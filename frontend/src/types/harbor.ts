import { SolutionResponse } from './solution';
import { TaskResponse } from './task';
import { TestSuiteResponse } from './testSuite';
import { ValidationReport } from './validation';

export type ValidationStatusLiteral = 'VALIDATED' | 'REJECTED' | 'NOT_VALIDATED';

export interface HarborTaskInfo {
  name: string;
  description: string;
}

export interface HarborMetadataConfig {
  difficulty: string;
  category: string;
  tags: string[];
  starting_commit_sha?: string | null;
  project_name: string;
  validation_status: ValidationStatusLiteral;
}

export interface HarborEnvironmentConfig {
  cpus?: number;
  memory_mb?: number;
  storage_mb?: number;
  allow_internet?: boolean;
  build_timeout_sec?: number;
}

export interface HarborAgentConfig {
  timeout_sec?: number;
}

export interface HarborVerifierConfig {
  timeout_sec?: number;
}

export interface HarborTaskManifest {
  schema_version: string;
  task: HarborTaskInfo;
  metadata: HarborMetadataConfig;
  environment: HarborEnvironmentConfig;
  agent: HarborAgentConfig;
  verifier: HarborVerifierConfig;
}

export interface HarborExportRequest {
  task: TaskResponse;
  solution: SolutionResponse;
  test_suite: TestSuiteResponse;
  validation_report?: ValidationReport | null;
  task_prefix?: string;
}

export interface HarborExportReport {
  task_id: string;
  harbor_task_name: string;
  export_directory: string;
  archive_path?: string | null;
  files_exported: string[];
  archive_size_bytes: number;
  validation_status_recorded: ValidationStatusLiteral;
  exported_at: string;
}
