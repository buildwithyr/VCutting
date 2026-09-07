/** Zugriff auf das Backend. Alle Downloads laufen ueber die API. */

import type { Job, ProjectConfig, ValidationReport } from '../types/project';

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api';

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface ErrorBody {
  detail?: unknown;
}

/** Uebersetzt eine Fehlerantwort in eine lesbare Meldung. */
export async function describeError(response: Response): Promise<string> {
  let body: ErrorBody | null = null;
  try {
    body = (await response.json()) as ErrorBody;
  } catch (error) {
    // Keine JSON-Antwort, zum Beispiel bei einem Proxy-Fehler.
    console.warn('Fehlerantwort ohne JSON-Inhalt:', error);
    return `Serverfehler ${response.status} ${response.statusText}`;
  }

  const detail = body?.detail;
  if (typeof detail === 'string') return detail;

  if (detail && typeof detail === 'object') {
    const record = detail as { message?: unknown; errors?: unknown };
    const parts: string[] = [];
    if (typeof record.message === 'string') parts.push(record.message);
    if (Array.isArray(record.errors)) {
      for (const item of record.errors as Array<{ loc?: unknown[]; msg?: string }>) {
        const field = Array.isArray(item.loc) ? item.loc.filter((l) => l !== 'body').join('.') : '';
        parts.push(field ? `${field}: ${item.msg ?? ''}` : String(item.msg ?? ''));
      }
    }
    if (parts.length > 0) return parts.join(' ');
  }

  return `Serverfehler ${response.status} ${response.statusText}`;
}

async function ensureOk(response: Response): Promise<Response> {
  if (!response.ok) {
    throw new ApiError(await describeError(response), response.status);
  }
  return response;
}

export async function getHealth(): Promise<{ status: string; schema_version: string; occ_available: boolean }> {
  const response = await ensureOk(await fetch(`${API_BASE}/health`));
  return response.json();
}

export async function createJob(image: File, config: ProjectConfig): Promise<Job> {
  const form = new FormData();
  form.append('image', image);
  form.append('config', JSON.stringify(config));
  const response = await ensureOk(await fetch(`${API_BASE}/jobs`, { method: 'POST', body: form }));
  return response.json();
}

export async function getJob(jobId: string): Promise<Job> {
  const response = await ensureOk(await fetch(`${API_BASE}/jobs/${jobId}`));
  return response.json();
}

export async function getReport(jobId: string): Promise<ValidationReport> {
  const response = await ensureOk(await fetch(`${API_BASE}/jobs/${jobId}/report`));
  return response.json();
}

export async function deleteJob(jobId: string): Promise<void> {
  await ensureOk(await fetch(`${API_BASE}/jobs/${jobId}`, { method: 'DELETE' }));
}

/** Validiert eine importierte Projektdatei serverseitig. */
export async function validateConfig(config: unknown): Promise<ProjectConfig> {
  const response = await ensureOk(
    await fetch(`${API_BASE}/config/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }),
  );
  return response.json();
}

export type PreviewKind = 'cleaned' | 'toolpath' | 'simulation';
export type DownloadKind = 'project' | 'step' | 'stl';

export function previewUrl(jobId: string, kind: PreviewKind): string {
  return `${API_BASE}/jobs/${jobId}/preview/${kind}`;
}

export function downloadUrl(jobId: string, kind: DownloadKind): string {
  return `${API_BASE}/jobs/${jobId}/download/${kind}`;
}

export function reportUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/report`;
}
