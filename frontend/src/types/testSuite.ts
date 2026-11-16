import { RepoAnalysisResponse } from './repo';
import { SolutionResponse } from './solution';
import { TaskResponse } from './task';

export type TestKind = 'feature' | 'regression';

export type TestCaseType =
  | 'happy_path'
  | 'edge_case'
  | 'invalid_input'
  | 'error_handling'
  | 'acceptance_criterion'
  | 'regression_check';

export interface TestCase {
  name: string;
  test_kind: TestKind;
  case_type: TestCaseType;
  description: string;
  target_criterion?: string | null;
  expected_behavior: string;
}

export interface TestFile {
  path: string;
  test_kind: TestKind;
  framework?: string;
  code: string;
  test_cases: TestCase[];
}

export interface RepositoryMetadata {
  project_name: string;
  source_type: 'github' | 'zip' | 'local' | 'unknown';
  starting_commit_sha?: string | null;
  detected_language: string;
  detected_frameworks: string[];
  test_framework: string;
  test_framework_config_file?: string | null;
  existing_test_files: string[];
  environment_info?: Record<string, string>;
}

export interface TestSuiteRequest {
  task: TaskResponse;
  solution?: SolutionResponse | null;
  repo_analysis?: RepoAnalysisResponse | null;
  starting_commit_sha?: string | null;
  preferred_framework?: string | null;
}

export interface TestSuiteResponse {
  id: string;
  task_id: string;
  task_title: string;
  repository: RepositoryMetadata;
  feature_test_files: TestFile[];
  regression_test_files: TestFile[];
  total_feature_tests: number;
  total_regression_tests: number;
  coverage_summary: string;
  execution_instructions: string;
  generated_at: string;
}
