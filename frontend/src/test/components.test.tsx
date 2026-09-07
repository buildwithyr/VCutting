import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { describeUploadProblem } from '../lib/uploadCheck';
import { Notices } from '../components/Notices';
import { NumberField } from '../components/NumberField';
import { StepPlate, StepTool } from '../components/steps/StepPlateTool';
import { StepExport, StepPreview } from '../components/steps/StepPreviewExport';
import { configNotices } from '../lib/toolCalc';
import type { Job, ProjectConfig, ValidationReport } from '../types/project';
import { defaultConfig } from '../types/project';

function renderTool(mutate: (config: ProjectConfig) => void = () => undefined) {
  const config = defaultConfig();
  mutate(config);
  const update = vi.fn();
  render(<StepTool config={config} update={update} notices={configNotices(config)} />);
  return { config, update };
}

describe('NumberField', () => {
  it('zeigt Beschriftung, Einheit und Hinweis', () => {
    render(<NumberField label="Plattenbreite" unit="mm" value={400} onChange={() => undefined} hint="Standard 400" />);
    expect(screen.getByLabelText(/Plattenbreite/)).toHaveValue(400);
    expect(screen.getByText('Standard 400')).toBeInTheDocument();
  });

  it('meldet eine gueltige Zahl weiter', () => {
    const onChange = vi.fn();
    render(<NumberField label="Tiefe" value={1.2} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/Tiefe/), { target: { value: '2.5' } });
    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenCalledWith(2.5);
  });

  it('setzt eine leere Eingabe nicht stillschweigend auf 0', () => {
    const onChange = vi.fn();
    render(<NumberField label="Tiefe" value={1.2} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/Tiefe/), { target: { value: '' } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('zeigt Fehler als Alert an', () => {
    render(<NumberField label="Tiefe" value={5} onChange={() => undefined} error="Zu tief" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Zu tief');
    expect(screen.getByLabelText(/Tiefe/)).toHaveAttribute('aria-invalid', 'true');
  });
});

describe('Schritt Werkzeug', () => {
  it('zeigt die Nutbreite bei 90 Grad', () => {
    renderTool();
    expect(screen.getByTestId('groove-width')).toHaveTextContent('2.40 mm');
    expect(screen.getByTestId('remaining-thickness')).toHaveTextContent('1.80 mm');
  });

  it('rechnet die Nutbreite bei einem anderen Winkel neu', () => {
    renderTool((config) => {
      config.tool.angle_deg = 60;
    });
    expect(screen.getByTestId('groove-width')).toHaveTextContent('1.39 mm');
    expect(screen.getByText(/Nutbreite 1.39 mm statt 2.40 mm/)).toBeInTheDocument();
  });

  it('warnt bei zu geringer Reststaerke', () => {
    renderTool((config) => {
      config.carving.max_depth_mm = 2.8;
      config.carving.line_spacing_mm = 6;
    });
    expect(screen.getByTestId('remaining-thickness')).toHaveTextContent('0.20 mm');
    expect(screen.getByText(/Die Platte kann brechen/)).toBeInTheDocument();
  });

  it('meldet eine Tiefe groesser als die Plattenstaerke als Fehler', () => {
    renderTool((config) => {
      config.carving.max_depth_mm = 4;
    });
    expect(screen.getAllByRole('alert').some((node) => node.textContent?.includes('durchtrennt'))).toBe(true);
  });

  it('reicht Aenderungen nach oben durch', async () => {
    const { update } = renderTool();
    await userEvent.clear(screen.getByLabelText(/V-Winkel/));
    await userEvent.type(screen.getByLabelText(/V-Winkel/), '60');
    expect(update).toHaveBeenCalled();
  });
});

describe('Schritt Platte', () => {
  it('zeigt die nutzbare Flaeche und das Koordinatensystem', () => {
    const config = defaultConfig();
    render(<StepPlate config={config} update={vi.fn()} notices={configNotices(config)} />);
    expect(screen.getByTestId('usable-area')).toHaveTextContent('360 x 360 mm');
    expect(screen.getByText('Z = -3.00 mm')).toBeInTheDocument();
  });

  it('meldet einen zu grossen Rand am Feld', () => {
    const config = defaultConfig();
    config.plate.margin_mm = 250;
    render(<StepPlate config={config} update={vi.fn()} notices={configNotices(config)} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Plattenrand');
  });
});

describe('Notices', () => {
  it('bleibt bei leerer Liste unsichtbar', () => {
    const { container } = render(<Notices notices={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('kennzeichnet Fehler als Alert', () => {
    render(<Notices notices={[{ severity: 'error', field: 'x', message: 'Kaputt' }]} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Kaputt');
  });
});

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    job_id: '3f2504e0-4f89-11d3-9a0c-0305e82c3301',
    status: 'completed',
    progress: 1,
    stage: 'completed',
    message: 'Fertig.',
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:10Z',
    config: defaultConfig(),
    metrics: {
      line_count: 185,
      connector_count: 184,
      raw_point_count: 163262,
      simplified_point_count: 1879,
      reduction_percent: 98.85,
      avg_points_per_line: 10.16,
      max_points_per_line: 16,
      cut_length_mm: 37166,
      travel_length_mm: 4510,
      min_z_mm: -1.1624,
      max_z_mm: 1,
      longest_connector_mm: 10.2,
      estimated_step_size_kb: 287.6,
      groove_width_mm: 2.4,
      remaining_thickness_mm: 1.8,
      motif_bbox_mm: [20, 64.5, 380, 335.5],
      mm_per_pixel: 0.25,
    },
    artifacts: {
      project: true,
      cleaned_png: true,
      toolpath_png: true,
      simulation_png: true,
      step: true,
      stl: false,
      report: true,
    },
    warnings: [],
    report_passed: true,
    ...overrides,
  };
}

describe('Schritt Vorschau', () => {
  it('zeigt Punktzahlen und Reduktion', () => {
    render(<StepPreview job={makeJob()} config={defaultConfig()} originalUrl={null} />);
    const metrics = screen.getByTestId('metrics');
    expect(metrics).toHaveTextContent('185');
    expect(metrics).toHaveTextContent('163.262');
    expect(metrics).toHaveTextContent('1.879');
    expect(screen.getByTestId('reduction')).toHaveTextContent('98.85 Prozent');
  });

  it('warnt bei zu geringer Reduktion', () => {
    const job = makeJob();
    job.metrics!.reduction_percent = 62;
    render(<StepPreview job={job} config={defaultConfig()} originalUrl={null} />);
    expect(screen.getByText(/Nur 62.0 Prozent Punktreduktion/)).toBeInTheDocument();
  });

  it('bleibt ohne Job leer', () => {
    render(<StepPreview job={null} config={defaultConfig()} originalUrl={null} />);
    expect(screen.getByText(/Noch kein Ergebnis/)).toBeInTheDocument();
    expect(screen.queryByTestId('metrics')).not.toBeInTheDocument();
  });
});

describe('Schritt Export', () => {
  it('aktiviert nur die vorhandenen Downloads', () => {
    render(
      <StepExport job={makeJob()} config={defaultConfig()} report={null} onExportProject={vi.fn()} />,
    );
    expect(screen.getByRole('link', { name: 'STEP-Datei' })).toHaveAttribute('download');
    // STL wurde in diesem Job nicht erzeugt.
    expect(screen.queryByRole('link', { name: 'STL-Datei' })).not.toBeInTheDocument();
    expect(screen.getByText('STL-Datei')).toHaveAttribute('aria-disabled', 'true');
  });

  it('sperrt alle Server-Downloads solange der Job laeuft', () => {
    const job = makeJob({ status: 'processing', progress: 0.5 });
    render(<StepExport job={job} config={defaultConfig()} report={null} onExportProject={vi.fn()} />);
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });

  it('exportiert das Projekt lokal', async () => {
    const onExportProject = vi.fn();
    render(
      <StepExport job={null} config={defaultConfig()} report={null} onExportProject={onExportProject} />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Projekt-JSON speichern' }));
    expect(onExportProject).toHaveBeenCalledOnce();
  });

  it('zeigt den Pruefbericht mit fehlgeschlagenen Zeilen', () => {
    const report: ValidationReport = {
      schema_version: '1.0',
      job_id: 'x',
      created_at: '2026-01-01T00:00:00Z',
      mode: 'v_cutting',
      passed: false,
      checks: [
        { name: 'step_lesbar', passed: true, detail: 'Datei geoeffnet.', value: null, expected: null },
        { name: 'punktreduktion', passed: false, detail: 'Nur 40 Prozent.', value: 40, expected: 'mindestens 85' },
      ],
      warnings: [],
      disclaimer: 'Vor dem Fraesen simulieren.',
    };
    render(<StepExport job={makeJob()} config={defaultConfig()} report={report} onExportProject={vi.fn()} />);
    expect(screen.getByText('nicht bestanden')).toBeInTheDocument();
    expect(screen.getByText('Nur 40 Prozent.')).toBeInTheDocument();
    expect(screen.getByText(/Erwartet: mindestens 85/)).toBeInTheDocument();
  });

  it('weist immer auf die Simulationspflicht hin', () => {
    render(<StepExport job={null} config={defaultConfig()} report={null} onExportProject={vi.fn()} />);
    expect(screen.getByText(/kein geprueftes Maschinenprogramm/)).toBeInTheDocument();
    expect(screen.getByText(/\.hop/)).toBeInTheDocument();
  });
});

describe('Upload-Pruefung', () => {
  function makeFile(name: string, type: string, size: number): File {
    const file = new File(['x'], name, { type });
    Object.defineProperty(file, 'size', { value: size });
    return file;
  }

  it('nimmt PNG, JPG und WebP an', () => {
    expect(describeUploadProblem(makeFile('a.png', 'image/png', 1000))).toBeNull();
    expect(describeUploadProblem(makeFile('a.jpg', 'image/jpeg', 1000))).toBeNull();
    expect(describeUploadProblem(makeFile('a.webp', 'image/webp', 1000))).toBeNull();
  });

  it('lehnt andere Formate ab', () => {
    expect(describeUploadProblem(makeFile('a.pdf', 'application/pdf', 1000))).toContain('nicht unterstuetzt');
  });

  it('lehnt Dateien ueber 20 MB ab', () => {
    expect(describeUploadProblem(makeFile('a.png', 'image/png', 21 * 1024 * 1024))).toContain('20 MB');
  });

  it('lehnt leere Dateien ab', () => {
    expect(describeUploadProblem(makeFile('a.png', 'image/png', 0))).toContain('leer');
  });
});

describe('Jobstatus in der Vorschau', () => {
  it('zeigt keine Bilder, solange der Job laeuft', async () => {
    const job = makeJob({ status: 'processing', progress: 0.4 });
    render(<StepPreview job={job} config={defaultConfig()} originalUrl={null} />);
    await waitFor(() => {
      expect(screen.queryByAltText('Bereinigtes Motiv')).not.toBeInTheDocument();
    });
  });

  it('zeigt die Bilder nach dem Abschluss', () => {
    render(<StepPreview job={makeJob()} config={defaultConfig()} originalUrl={null} />);
    expect(screen.getByAltText('Bereinigtes Motiv')).toBeInTheDocument();
    expect(screen.getByAltText('Vorschau der Fraesbahn')).toBeInTheDocument();
  });
});
