import { SolutionResponse } from './solution';
import { TaskResponse } from './task';
import { TestSuiteResponse } from './testSuite';

export type ExecutionMode = 'static' | 'trusted_local' | 'isolated' | 'harbor';
export type OverallVerdict = 'VALIDATED' | 'REJECTED' | 'NOT_VALIDATED';
export type BaselineStatus = 'passed' | 'failed' | 'not_run' | 'skipped';
export type MutationStatus = 'passed' | 'failed' | 'not_run';

export interface TestExecutionResult {
  test_file: string;
  test_kind: string;
  exit_code: number;
  duration_ms: number;
  stdout: string;
  stderr: string;
  passed: boolean;
  individual_cases?: Array<Record<string, unknown>>;
}

export interface ValidationReport {
  id: string;
  task_id: string;
  solution_id: string;
  test_suite_id: string;
  starting_commit_sha?: string | null;
  execution_mode: ExecutionMode;
  baseline_status: BaselineStatus;
  baseline_result?: TestExecutionResult | null;
  solution_applied_successfully: boolean;
  created_files: string[];
  modified_files: string[];
  feature_tests_result?: TestExecutionResult | null;
  regression_tests_result?: TestExecutionResult | null;
  mutation_test_status: MutationStatus;
  mutation_test_result?: TestExecutionResult | null;
  overall_verdict: OverallVerdict;
  rejection_reasons: string[];
  execution_duration_ms: number;
  created_at: string;
}

export interface ValidationRequest {
  task: TaskResponse;
  solution: SolutionResponse;
  test_suite: TestSuiteResponse;
  execution_mode?: ExecutionMode;
  starting_commit_sha?: string | null;
}
