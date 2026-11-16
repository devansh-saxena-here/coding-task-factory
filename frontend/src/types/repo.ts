export interface RepoAnalysisRequest {
  repo_url: string;
}

export interface RepoAnalysisResponse {
  project_name: string;
  source_type: 'github' | 'zip';
  detected_languages: string[];
  detected_frameworks: string[];
  file_count: number;
  folder_structure: string[];
  readme_summary: string | null;
  analysis_status: 'pending' | 'completed' | 'failed';
  commit_sha: string | null;
}
