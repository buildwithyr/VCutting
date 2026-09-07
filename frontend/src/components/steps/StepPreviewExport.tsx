import { downloadUrl, previewUrl, reportUrl } from '../../api/client';
import { formatBytesFromKb, reductionNotice } from '../../lib/toolCalc';
import type { Job, ProjectConfig, ValidationReport } from '../../types/project';
import { Notices } from '../Notices';

interface PreviewProps {
  job: Job | null;
  config: ProjectConfig;
  originalUrl: string | null;
}

export function StepPreview({ job, config, originalUrl }: PreviewProps) {
  const metrics = job?.metrics ?? null;
  const ready = job?.status === 'completed';
  const reduction = metrics ? reductionNotice(metrics.reduction_percent) : null;

  return (
    <section className="step">
      <h2>Schritt 5: Vorschau</h2>

      {!job ? (
        <p className="step__lead">
          Noch kein Ergebnis. Bild waehlen, Werte pruefen und die Berechnung starten.
        </p>
      ) : null}

      <div className="preview-grid">
        {originalUrl ? (
          <figure>
            <figcaption>Originalbild</figcaption>
            <div className="checkerboard">
              <img src={originalUrl} alt="Originalbild" />
            </div>
          </figure>
        ) : null}

        {ready && job?.artifacts.cleaned_png ? (
          <figure>
            <figcaption>Bereinigtes Motiv</figcaption>
            <div className="checkerboard">
              <img src={previewUrl(job.job_id, 'cleaned')} alt="Bereinigtes Motiv" />
            </div>
          </figure>
        ) : null}

        {ready && job?.artifacts.toolpath_png ? (
          <figure>
            <figcaption>
              {config.mode === 'relief'
                ? 'Hoehenkarte'
                : 'Fraesbahn: rot schneidet, blau faehrt auf Sicherheits-Z, gruen ist die Motivkontur, schwarz die Platte'}
            </figcaption>
            <img src={previewUrl(job.job_id, 'toolpath')} alt="Vorschau der Fraesbahn" />
          </figure>
        ) : null}

        {ready && job?.artifacts.simulation_png ? (
          <figure>
            <figcaption>Simuliertes Fraesbild</figcaption>
            <img src={previewUrl(job.job_id, 'simulation')} alt="Simuliertes Fraesbild" />
          </figure>
        ) : null}
      </div>

      {metrics ? (
        <dl className="readout readout--wide" data-testid="metrics">
          <div>
            <dt>Anzahl der Linien</dt>
            <dd>{metrics.line_count}</dd>
          </div>
          <div>
            <dt>Verbindungen</dt>
            <dd>{metrics.connector_count}</dd>
          </div>
          <div>
            <dt>Punkte vor der Vereinfachung</dt>
            <dd>{metrics.raw_point_count.toLocaleString('de-DE')}</dd>
          </div>
          <div>
            <dt>Punkte nach der Vereinfachung</dt>
            <dd>{metrics.simplified_point_count.toLocaleString('de-DE')}</dd>
          </div>
          <div>
            <dt>Reduktion</dt>
            <dd data-testid="reduction">{metrics.reduction_percent.toFixed(2)} Prozent</dd>
          </div>
          <div>
            <dt>Punkte je Linie</dt>
            <dd>
              {metrics.avg_points_per_line} im Mittel, {metrics.max_points_per_line} maximal
            </dd>
          </div>
          <div>
            <dt>Geschaetzte STEP-Groesse</dt>
            <dd>{formatBytesFromKb(metrics.estimated_step_size_kb)}</dd>
          </div>
          <div>
            <dt>Z-Bereich</dt>
            <dd>
              {metrics.min_z_mm} bis {metrics.max_z_mm} mm
            </dd>
          </div>
          <div>
            <dt>Laengste Verbindung</dt>
            <dd>{metrics.longest_connector_mm} mm</dd>
          </div>
        </dl>
      ) : null}

      {reduction ? <Notices notices={[reduction]} /> : null}
    </section>
  );
}

interface ExportProps {
  job: Job | null;
  config: ProjectConfig;
  report: ValidationReport | null;
  onExportProject: () => void;
}

export function StepExport({ job, config, report, onExportProject }: ExportProps) {
  const ready = job?.status === 'completed';
  const artifacts = job?.artifacts;

  return (
    <section className="step">
      <h2>Schritt 6: Export</h2>

      <div className="downloads">
        <button type="button" onClick={onExportProject}>
          Projekt-JSON speichern
        </button>
        <DownloadLink
          href={ready && artifacts?.project ? downloadUrl(job.job_id, 'project') : null}
          label="Projektdatei vom Server"
        />
        <DownloadLink
          href={ready && artifacts?.cleaned_png ? previewUrl(job.job_id, 'cleaned') : null}
          label="Bereinigtes PNG"
        />
        <DownloadLink
          href={ready && artifacts?.toolpath_png ? previewUrl(job.job_id, 'toolpath') : null}
          label="Bahn-Vorschau als PNG"
        />
        <DownloadLink
          href={ready && artifacts?.step ? downloadUrl(job.job_id, 'step') : null}
          label="STEP-Datei"
        />
        <DownloadLink
          href={ready && artifacts?.stl ? downloadUrl(job.job_id, 'stl') : null}
          label="STL-Datei"
        />
        <DownloadLink
          href={ready && artifacts?.report ? reportUrl(job.job_id) : null}
          label="Pruefbericht als JSON"
        />
      </div>

      {report ? (
        <div className="report">
          <h3>
            Technischer Pruefbericht:{' '}
            <span className={report.passed ? 'badge badge--ok' : 'badge badge--fail'}>
              {report.passed ? 'bestanden' : 'nicht bestanden'}
            </span>
          </h3>
          <table>
            <thead>
              <tr>
                <th>Pruefung</th>
                <th>Ergebnis</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {report.checks.map((check) => (
                <tr key={check.name} className={check.passed ? undefined : 'row--fail'}>
                  <td>{check.name}</td>
                  <td>{check.passed ? 'ok' : 'Fehler'}</td>
                  <td>
                    {check.detail}
                    {check.expected ? <em> Erwartet: {check.expected}</em> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="disclaimer">{report.disclaimer}</p>
        </div>
      ) : null}

      <p className="disclaimer">
        Die erzeugte STEP-Datei enthaelt reine Geometrie und ist kein geprueftes Maschinenprogramm.
        Vor dem Fraesen ist eine Simulation in CATIA beziehungsweise im NC-Postprozessor zwingend
        erforderlich. Vorschuebe und Drehzahlen werden bewusst nicht vorgegeben. Die Formate .hop
        und .hopx sind postprozessorspezifisch und werden hier nicht erzeugt.
      </p>

      {config.mode === 'relief' ? (
        <p className="disclaimer">
          Ein fein trianguliertes Relief wird bewusst nicht als facettiertes STEP exportiert. Der
          Speicherbedarf im STEP-Uebersetzer waere unverhaeltnismaessig hoch.
        </p>
      ) : null}
    </section>
  );
}

function DownloadLink({ href, label }: { href: string | null; label: string }) {
  if (!href) {
    return (
      <span className="download download--disabled" aria-disabled="true">
        {label}
      </span>
    );
  }
  return (
    <a className="download" href={href} download>
      {label}
    </a>
  );
}
