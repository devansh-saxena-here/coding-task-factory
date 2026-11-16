/**
 * Centralized API Client for Coding Task Factory Backend.
 *
 * Configured via VITE_API_BASE_URL.
 * Supports typed JSON calls, multipart ZIP uploads, and binary ZIP archive downloads.
 * Never exposes AI secrets or keys in client code.
 */

import { ApiError } from '../types/api';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

async function parseResponseError(response: Response): Promise<ApiError> {
  let detailMessage = `Request failed with status ${response.status}`;
  let detailData: unknown = undefined;

  try {
    const data = await response.json();
    detailData = data;
    if (data && typeof data === 'object') {
      if (typeof data.detail === 'string') {
        detailMessage = data.detail;
      } else if (Array.isArray(data.detail)) {
        // Pydantic validation error array
        detailMessage = data.detail.map((err: { msg?: string; loc?: string[] }) => err.msg || 'Validation error').join(', ');
      } else if (typeof data.message === 'string') {
        detailMessage = data.message;
      }
    }
  } catch {
    // If not JSON, try text
    try {
      const text = await response.text();
      if (text) detailMessage = text;
    } catch {
      // Keep default
    }
  }

  return {
    message: detailMessage,
    statusCode: response.status,
    detail: typeof detailData === 'object' && detailData !== null ? (detailData as Record<string, unknown>) : detailMessage,
  };
}

export async function requestJson<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await parseResponseError(response);
      throw error;
    }

    return (await response.json()) as T;
  } catch (err: unknown) {
    if ((err as ApiError)?.message) {
      throw err;
    }
    throw {
      message: (err as Error)?.message || 'Network request failed or server is unreachable.',
      statusCode: 0,
    } as ApiError;
  }
}

export async function requestMultipart<T>(
  endpoint: string,
  formData: FormData
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      // Note: Do NOT set Content-Type header; browser sets multipart/form-data boundary automatically
    });

    if (!response.ok) {
      const error = await parseResponseError(response);
      throw error;
    }

    return (await response.json()) as T;
  } catch (err: unknown) {
    if ((err as ApiError)?.message) {
      throw err;
    }
    throw {
      message: (err as Error)?.message || 'File upload failed.',
      statusCode: 0,
    } as ApiError;
  }
}

export interface DownloadResult {
  blob: Blob;
  filename: string;
  harborTaskName?: string;
  validationStatus?: string;
}

export async function requestBlob(
  endpoint: string,
  options: RequestInit = {}
): Promise<DownloadResult> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await parseResponseError(response);
      throw error;
    }

    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition') || '';
    let filename = 'task-package.zip';

    const match = disposition.match(/filename="?([^";]+)"?/i);
    if (match && match[1]) {
      filename = match[1].trim();
    }

    return {
      blob,
      filename,
      harborTaskName: response.headers.get('x-harbor-task-name') || undefined,
      validationStatus: response.headers.get('x-validation-status') || undefined,
    };
  } catch (err: unknown) {
    if ((err as ApiError)?.message) {
      throw err;
    }
    throw {
      message: (err as Error)?.message || 'Download failed.',
      statusCode: 0,
    } as ApiError;
  }
}
