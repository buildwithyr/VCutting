import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../App';
import { describeError } from '../api/client';
import type { Job } from '../types/project';
import { defaultConfig } from '../types/project';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function completedJob(): Job {
  return {
    job_id: '3f2504e0-4f89-11d3-9a0c-0305e82c3301',
    status: 'completed',
    progress: 1,
    stage: 'completed',
    message: 'Fertig. Alle Dateien stehen zum Download bereit.',
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:05Z',
    config: defaultConfig(),
    metrics: null,
    artifacts: {
      project: true,
      cleaned_png: true,
      toolpath_png: true,
      simulation_png: true,
      step: true,
      stl: false,
      report: false,
    },
    warnings: ['Nutbreite 2.40 mm ist groesser als der Linienabstand 2.00 mm.'],
    report_passed: true,
  };
}

function pngFile(name = 'motiv.png', size = 4096): File {
  const file = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], name, { type: 'image/png' });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  it('zeigt alle sechs Schritte', () => {
    render(<App />);
    for (const label of ['Bild', 'Platte', 'Werkzeug', 'Bahn', 'Vorschau', 'Export']) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }
  });

  it('sperrt den Start ohne Bild', () => {
    render(<App />);
    expect(screen.getByRole('button', { name: /Berechnung starten/ })).toBeDisabled();
    expect(screen.getByText('Zuerst ein Bild auswaehlen.')).toBeInTheDocument();
  });

  it('wechselt den Schritt ueber die Navigation', async () => {
    render(<App />);
    await userEvent.click(screen.getByRole('button', { name: /Werkzeug/ }));
    expect(screen.getByRole('heading', { name: 'Schritt 3: Werkzeug' })).toBeInTheDocument();
    expect(screen.getByTestId('groove-width')).toHaveTextContent('2.40 mm');
  });

  it('startet einen Job und zeigt den Fortschritt', async () => {
    const job = completedJob();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/jobs')) return jsonResponse(job, 202);
      if (url.includes(`/jobs/${job.job_id}`)) return jsonResponse(job);
      return jsonResponse({}, 404);
    });

    render(<App />);
    await userEvent.upload(screen.getByLabelText('Bilddatei auswaehlen'), pngFile());
    await userEvent.click(screen.getByRole('button', { name: /Berechnung starten/ }));

    await waitFor(() => {
      expect(screen.getByTestId('job-progress')).toHaveTextContent('completed');
    });
    expect(screen.getByRole('heading', { name: 'Schritt 5: Vorschau' })).toBeInTheDocument();
    // Der Hinweis steht sowohl bei den Eingabepruefungen als auch bei den
    // Jobwarnungen; beide Stellen sollen ihn zeigen.
    expect(screen.getAllByText(/Nutbreite 2.40 mm/).length).toBeGreaterThanOrEqual(2);
  });

  it('zeigt einen Serverfehler verstaendlich an', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: 'Das Bild ist beschaedigt oder unvollstaendig.' }, 422),
    );

    render(<App />);
    await userEvent.upload(screen.getByLabelText('Bilddatei auswaehlen'), pngFile());
    await userEvent.click(screen.getByRole('button', { name: /Berechnung starten/ }));

    await waitFor(() => {
      expect(
        screen.getByText('Das Bild ist beschaedigt oder unvollstaendig.'),
      ).toBeInTheDocument();
    });
  });

  it('meldet einen fehlgeschlagenen Job', async () => {
    const job = completedJob();
    const failed: Job = { ...job, status: 'failed', error: 'Es wurde kein Motiv gefunden.' };
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/jobs')) return jsonResponse({ ...job, status: 'queued' }, 202);
      return jsonResponse(failed);
    });

    render(<App />);
    await userEvent.upload(screen.getByLabelText('Bilddatei auswaehlen'), pngFile());
    await userEvent.click(screen.getByRole('button', { name: /Berechnung starten/ }));

    await waitFor(() => {
      expect(screen.getByText('Es wurde kein Motiv gefunden.')).toBeInTheDocument();
    });
  });

  it('lehnt eine zu grosse Datei bereits im Browser ab', async () => {
    render(<App />);
    const big = pngFile('gross.png', 25 * 1024 * 1024);
    await userEvent.upload(screen.getByLabelText('Bilddatei auswaehlen'), big);
    expect(screen.getByRole('alert')).toHaveTextContent('20 MB');
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it('importiert eine Projektdatei und uebernimmt die Werte', async () => {
    const imported = defaultConfig();
    imported.project.name = 'Importiert';
    imported.tool.angle_deg = 60;
    imported.carving.max_depth_mm = 1;
    vi.mocked(fetch).mockResolvedValue(jsonResponse(imported));

    render(<App />);
    const file = new File([JSON.stringify(imported)], 'projekt.json', { type: 'application/json' });
    await userEvent.upload(screen.getByLabelText('Projektdatei importieren'), file);

    await userEvent.click(screen.getByRole('button', { name: /Werkzeug/ }));
    await waitFor(() => {
      expect(screen.getByLabelText(/V-Winkel/)).toHaveValue(60);
    });
    expect(screen.getByTestId('groove-width')).toHaveTextContent('1.15 mm');
  });

  it('meldet eine kaputte Projektdatei', async () => {
    render(<App />);
    const file = new File(['{kaputt'], 'projekt.json', { type: 'application/json' });
    await userEvent.upload(screen.getByLabelText('Projektdatei importieren'), file);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('kein gueltiges JSON');
    });
  });

  it('meldet eine unbekannte Schemaversion', async () => {
    render(<App />);
    const file = new File([JSON.stringify({ schema_version: '2.0' })], 'projekt.json', {
      type: 'application/json',
    });
    await userEvent.upload(screen.getByLabelText('Projektdatei importieren'), file);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('schema_version');
    });
  });
});

describe('describeError', () => {
  it('nimmt eine einfache Detailmeldung', async () => {
    expect(await describeError(jsonResponse({ detail: 'Kaputt' }, 422))).toBe('Kaputt');
  });

  it('faltet Pydantic-Fehlerlisten zusammen', async () => {
    const body = {
      detail: {
        message: 'Die Konfiguration ist ungueltig.',
        errors: [{ loc: ['body', 'plate', 'width_mm'], msg: 'muss groesser als 0 sein' }],
      },
    };
    const text = await describeError(jsonResponse(body, 422));
    expect(text).toContain('Die Konfiguration ist ungueltig.');
    expect(text).toContain('plate.width_mm: muss groesser als 0 sein');
  });

  it('kommt ohne JSON-Antwort zurecht', async () => {
    const response = new Response('<html>502</html>', { status: 502, statusText: 'Bad Gateway' });
    expect(await describeError(response)).toContain('502');
  });
});
