import { useEffect, useState } from 'react';
import type { components } from './generated/api';
import { get } from './api';

export type Snapshot = components['schemas']['PopulationSnapshot'];
export type Evidence = components['schemas']['PopulationEvidence'];
export type PopulationMapData = components['schemas']['PopulationMap'];
export type Municipality = components['schemas']['PopulationMunicipality'];
export type Distribution = components['schemas']['PopulationDistribution'];
export type Validation = components['schemas']['PopulationValidation'];
export type Comparison = components['schemas']['PopulationComparison'];
export type Person = components['schemas']['SyntheticPerson'];
export type PersonPage = components['schemas']['SyntheticPersonPage'];
export type HouseholdPage = components['schemas']['SyntheticHouseholdPage'];
export type Household = components['schemas']['SyntheticHouseholdDetail'];
export const number = new Intl.NumberFormat('it-IT');
export const repositoryUrl = 'https://github.com/matik81/itadb';
export function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values))
    if (value !== undefined && value !== '') params.set(key, String(value));
  return params.toString();
}
export function useResource<T>(path: string | null) {
  const [state, setState] = useState<{
    path: string | null;
    data: T | null;
    error: string;
    loading: boolean;
  }>({ path: null, data: null, error: '', loading: false });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    if (!path) {
      setState({ path, data: null, error: '', loading: false });
      return;
    }
    setState({ path, data: null, error: '', loading: true });
    get<T>(path, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ path, data, error: '', loading: false });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ path, data: null, error: String(error.message), loading: false });
      });
    return () => controller.abort();
  }, [path, attempt]);
  return {
    ...(state.path === path ? state : { data: null, error: '', loading: !!path }),
    retry: () => setAttempt((a) => a + 1),
  };
}
