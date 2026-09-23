import type { components } from './generated/api';

export type Release = components['schemas']['ReleaseV2'];
export type Source = components['schemas']['Source'];
export type Page = components['schemas']['ObservationPageV2'];
export type Quality = components['schemas']['Quality'];
export type Artifact = components['schemas']['Artifact'];
export type Coverage = components['schemas']['CoverageItem'];
export type CrosswalkPage = components['schemas']['CrosswalkPage'];
export type Boundary = components['schemas']['BoundaryItem'];
export type Observation = components['schemas']['ObservationV2'];
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(
  /\/$/,
  '',
);

export async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!response.ok)
    throw new Error(`Il servizio ha risposto con errore ${response.status}. Riprova tra poco.`);
  return response.json() as Promise<T>;
}
