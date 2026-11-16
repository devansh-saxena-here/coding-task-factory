import { TaskResponse } from './task';

export type FileStatus = 'create' | 'modify';

export interface SolutionFile {
  path: string;
  status: FileStatus;
  language: string;
  code: string;
  explanation: string;
}

export interface SolutionRequest {
  task: TaskResponse;
}

export interface SolutionResponse {
  id: string;
  task_id: string;
  task_title: string;
  architecture_notes: string;
  files: SolutionFile[];
  testing_guide: string;
  verification_steps: string[];
  generated_at: string;
}
