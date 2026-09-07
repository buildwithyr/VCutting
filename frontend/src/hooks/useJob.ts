import { useCallback, useEffect, useRef, useState } from 'react';

import { createJob, getJob, getReport } from '../api/client';
import type { Job, ProjectConfig, ValidationReport } from '../types/project';

const POLL_INTERVAL_MS = 900;

export interface JobState {
  job: Job | null;
  report: ValidationReport | null;
  error: string | null;
  busy: boolean;
  start: (image: File, config: ProjectConfig) => Promise<void>;
  reset: () => void;
  dismissError: () => void;
}

/** Startet einen Job und verfolgt seinen Status bis zum Ende. */
export function useJob(): JobState {
  const [job, setJob] = useState<Job | null>(null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollTimer = useRef<number | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
    };
  }, []);

  const poll = useCallback(async (jobId: string) => {
    try {
      const current = await getJob(jobId);
      if (!mounted.current) return;
      setJob(current);

      if (current.status === 'completed') {
        setBusy(false);
        if (current.artifacts.report) {
          try {
            setReport(await getReport(jobId));
          } catch (reportError) {
            // Der Bericht ist nur eine Zusatzinformation, der Job bleibt gueltig.
            console.warn('Pruefbericht konnte nicht geladen werden:', reportError);
          }
        }
        return;
      }

      if (current.status === 'failed') {
        setBusy(false);
        setError(current.error ?? 'Die Verarbeitung ist fehlgeschlagen.');
        return;
      }

      pollTimer.current = window.setTimeout(() => void poll(jobId), POLL_INTERVAL_MS);
    } catch (pollError) {
      if (!mounted.current) return;
      setBusy(false);
      setError(pollError instanceof Error ? pollError.message : String(pollError));
    }
  }, []);

  const start = useCallback(
    async (image: File, config: ProjectConfig) => {
      setError(null);
      setReport(null);
      setBusy(true);
      try {
        const created = await createJob(image, config);
        if (!mounted.current) return;
        setJob(created);
        await poll(created.job_id);
      } catch (startError) {
        if (!mounted.current) return;
        setBusy(false);
        setError(startError instanceof Error ? startError.message : String(startError));
      }
    },
    [poll],
  );

  const reset = useCallback(() => {
    if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
    setJob(null);
    setReport(null);
    setError(null);
    setBusy(false);
  }, []);

  return { job, report, error, busy, start, reset, dismissError: () => setError(null) };
}
