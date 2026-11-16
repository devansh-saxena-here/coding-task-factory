/**
 * Task Service — high-level typed API operations against the FastAPI backend.
 */

import { requestBlob, requestJson, requestMultipart, DownloadResult } from './api';
import { RepoAnalysisRequest, RepoAnalysisResponse } from '../types/repo';
import {
  GenerateFromGithubRequest,
  GenerateFromRepoRequest,
  TaskRequest,
  TaskResponse,
} from '../types/task';
import { SolutionRequest, SolutionResponse } from '../types/solution';
import { TestSuiteRequest, TestSuiteResponse } from '../types/testSuite';
import { ValidationReport, ValidationRequest } from '../types/validation';
import { HarborExportRequest } from '../types/harbor';

export const taskService = {
  /**
   * Health probe to verify backend connectivity.
   */
  async checkHealth(): Promise<{ status: string }> {
    return requestJson<{ status: string }>('/health', { method: 'GET' });
  },

  /**
   * List existing tasks (placeholder from backend).
   */
  async listTasks(): Promise<{ tasks: TaskResponse[]; message: string }> {
    return requestJson<{ tasks: TaskResponse[]; message: string }>('/tasks/', { method: 'GET' });
  },

  /**
   * Topic-based standalone task generation.
   */
  async generateTopicTask(payload: TaskRequest): Promise<TaskResponse> {
    return requestJson<TaskResponse>('/tasks/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Analyze a public GitHub repository.
   */
  async analyzeGithub(payload: RepoAnalysisRequest): Promise<RepoAnalysisResponse> {
    return requestJson<RepoAnalysisResponse>('/tasks/analyze/github', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Analyze an uploaded ZIP archive of a repository.
   */
  async analyzeUpload(file: File): Promise<RepoAnalysisResponse> {
    const formData = new FormData();
    formData.append('file', file);
    return requestMultipart<RepoAnalysisResponse>('/tasks/analyze/upload', formData);
  },

  /**
   * Generate a contextual task grounded on an analyzed repository.
   */
  async generateTaskFromRepo(payload: GenerateFromRepoRequest): Promise<TaskResponse> {
    return requestJson<TaskResponse>('/tasks/generate/from-repo', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Combined endpoint: Analyze GitHub repo and generate contextual task.
   */
  async generateTaskFromGithub(payload: GenerateFromGithubRequest): Promise<TaskResponse> {
    return requestJson<TaskResponse>('/tasks/generate/github', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Generate canonical reference solution for a task.
   */
  async generateSolution(payload: SolutionRequest): Promise<SolutionResponse> {
    return requestJson<SolutionResponse>('/tasks/solution', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Synthesize automated repository-aware test suite.
   */
  async generateTestSuite(payload: TestSuiteRequest): Promise<TestSuiteResponse> {
    return requestJson<TestSuiteResponse>('/tasks/tests', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Validate task package through the 5 validation gates.
   */
  async validateTaskPackage(payload: ValidationRequest): Promise<ValidationReport> {
    return requestJson<ValidationReport>('/tasks/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Package and export validated evaluation task as Harbor 1.4 compliant ZIP archive.
   */
  async exportHarborTask(payload: HarborExportRequest): Promise<DownloadResult> {
    return requestBlob('/tasks/export/harbor', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};
