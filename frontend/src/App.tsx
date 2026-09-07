import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { validateConfig } from './api/client';
import { ImageDropzone } from './components/ImageDropzone';
import { ErrorBanner, Notices } from './components/Notices';
import { StepPath } from './components/steps/StepPath';
import { StepPlate, StepTool } from './components/steps/StepPlateTool';
import { StepExport, StepPreview } from './components/steps/StepPreviewExport';
import { useJob } from './hooks/useJob';
import { ProjectFileError, downloadFilename, parseProjectFile, projectToJson } from './lib/projectFile';
import { configNotices, hasBlockingError } from './lib/toolCalc';
import type { ProjectConfig } from './types/project';
import { defaultConfig } from './types/project';

const STEPS = ['Bild', 'Platte', 'Werkzeug', 'Bahn', 'Vorschau', 'Export'] as const;

export default function App() {
  const [config, setConfig] = useState<ProjectConfig>(defaultConfig);
  const [file, setFile] = useState<File | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const projectInputRef = useRef<HTMLInputElement>(null);

  const { job, report, error, busy, start, reset, dismissError } = useJob();

  useEffect(() => {
    if (!file) {
      setOriginalUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setOriginalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const notices = useMemo(() => configNotices(config), [config]);
  const blocked = hasBlockingError(config);

  const update = useCallback((patch: Partial<ProjectConfig>) => {
    setConfig((current) => ({ ...current, ...patch }));
  }, []);

  const handleStart = useCallback(async () => {
    if (!file || blocked) return;
    await start(file, config);
    setActiveStep(4);
  }, [file, blocked, start, config]);

  const handleExportProject = useCallback(() => {
    const blob = new Blob([projectToJson(config)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = downloadFilename(config, '.json');
    anchor.click();
    URL.revokeObjectURL(url);
  }, [config]);

  const handleImportProject = useCallback(async (selected: File) => {
    setUploadError(null);
    try {
      const parsed = parseProjectFile(await selected.text());
      // Der Server ergaenzt Vorbelegungen und prueft alle Wertebereiche.
      try {
        setConfig(await validateConfig(parsed));
      } catch (serverError) {
        // Ohne erreichbares Backend bleibt die lokal gepruefte Fassung nutzbar.
        console.warn('Serverseitige Pruefung nicht moeglich:', serverError);
        setConfig(parsed);
      }
    } catch (importError) {
      setUploadError(
        importError instanceof ProjectFileError
          ? importError.message
          : `Die Projektdatei konnte nicht gelesen werden: ${String(importError)}`,
      );
    }
  }, []);

  return (
    <div className="app">
      <header className="app__header">
        <div>
          <h1>Image to V-Cutting</h1>
          <p>Bilder werden zu CATIA-kompatiblen V-Carving-Bahnen und STEP-Dateien.</p>
        </div>
        <div className="app__actions">
          <button type="button" onClick={handleExportProject}>
            Projekt exportieren
          </button>
          <button type="button" onClick={() => projectInputRef.current?.click()}>
            Projekt importieren
          </button>
          <input
            ref={projectInputRef}
            type="file"
            accept="application/json,.json"
            className="visually-hidden"
            aria-label="Projektdatei importieren"
            onChange={(event) => {
              const selected = event.target.files?.[0];
              if (selected) void handleImportProject(selected);
              event.target.value = '';
            }}
          />
        </div>
      </header>

      <nav className="stepper" aria-label="Arbeitsschritte">
        {STEPS.map((label, index) => (
          <button
            key={label}
            type="button"
            className={`stepper__item${index === activeStep ? ' stepper__item--active' : ''}`}
            aria-current={index === activeStep ? 'step' : undefined}
            onClick={() => setActiveStep(index)}
          >
            <span className="stepper__number">{index + 1}</span>
            {label}
          </button>
        ))}
      </nav>

      {uploadError ? <ErrorBanner message={uploadError} onDismiss={() => setUploadError(null)} /> : null}
      {error ? <ErrorBanner message={error} onDismiss={dismissError} /> : null}

      <main>
        {activeStep === 0 ? (
          <section className="step">
            <h2>Schritt 1: Bild</h2>
            <p className="step__lead">
              Unterstuetzt werden PNG, JPG und WebP bis 20 MB. Transparenz wird als Schachbrett
              dargestellt und dient als Motivmaske.
            </p>
            <ImageDropzone file={file} onSelect={setFile} onReject={setUploadError} />
          </section>
        ) : null}

        {activeStep === 1 ? <StepPlate config={config} update={update} notices={notices} /> : null}
        {activeStep === 2 ? <StepTool config={config} update={update} notices={notices} /> : null}
        {activeStep === 3 ? (
          <StepPath config={config} update={update} replace={setConfig} notices={notices} />
        ) : null}
        {activeStep === 4 ? <StepPreview job={job} config={config} originalUrl={originalUrl} /> : null}
        {activeStep === 5 ? (
          <StepExport job={job} config={config} report={report} onExportProject={handleExportProject} />
        ) : null}
      </main>

      <aside className="sidebar">
        <Notices notices={notices} title="Pruefung der Eingaben" />

        <div className="run">
          <button
            type="button"
            className="run__button"
            disabled={!file || blocked || busy}
            onClick={() => void handleStart()}
          >
            {busy ? 'Berechnung laeuft ...' : 'Berechnung starten'}
          </button>
          {!file ? <p className="run__hint">Zuerst ein Bild auswaehlen.</p> : null}
          {blocked ? <p className="run__hint">Zuerst die Fehler oben beheben.</p> : null}

          {job ? (
            <div className="progress" data-testid="job-progress">
              <div className="progress__bar">
                <div className="progress__fill" style={{ width: `${Math.round(job.progress * 100)}%` }} />
              </div>
              <p>
                <strong>{job.status}</strong> - {job.message}
              </p>
              {job.warnings.length > 0 ? (
                <ul className="progress__warnings">
                  {job.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
              <button type="button" onClick={reset}>
                Ergebnis verwerfen
              </button>
            </div>
          ) : null}
        </div>

        <div className="coords">
          <h3>Koordinatensystem</h3>
          <ul>
            <li>X0/Y0 in der linken unteren Plattenecke</li>
            <li>Plattenoberseite Z = 0</li>
            <li>Plattenunterseite Z = {(config.plate.top_z_mm - config.plate.thickness_mm).toFixed(2)} mm</li>
            <li>Sicherheitsfahrt Z = +{config.carving.clearance_z_mm} mm</li>
            <li>Frästiefen negativ, hoechstens {config.carving.max_depth_mm} mm</li>
          </ul>
        </div>
      </aside>

      <footer className="app__footer">
        STEP ist reine Geometrie und kein geprueftes Maschinenprogramm. Vor dem Fraesen immer in
        CATIA beziehungsweise im NC-Postprozessor simulieren.
      </footer>
    </div>
  );
}
