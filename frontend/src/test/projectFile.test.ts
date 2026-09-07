import { describe, expect, it } from 'vitest';

import {
  ProjectFileError,
  applySimplificationMode,
  downloadFilename,
  migrateProject,
  parseProjectFile,
  projectToJson,
} from '../lib/projectFile';
import { SCHEMA_VERSION, SIMPLIFICATION_PRESETS, defaultConfig } from '../types/project';

describe('Projektdatei exportieren und importieren', () => {
  it('ueberlebt einen vollstaendigen Umlauf', () => {
    const original = defaultConfig();
    original.project.name = 'Oskar V-Cutting';
    original.plate.width_mm = 300;
    original.tool.angle_deg = 60;

    const restored = parseProjectFile(projectToJson(original));
    expect(restored.project.name).toBe('Oskar V-Cutting');
    expect(restored.plate.width_mm).toBe(300);
    expect(restored.tool.angle_deg).toBe(60);
    expect(restored.schema_version).toBe(SCHEMA_VERSION);
  });

  it('ergaenzt einen Zeitstempel beim Export', () => {
    const exported = JSON.parse(projectToJson(defaultConfig()));
    expect(typeof exported.project.created_at).toBe('string');
    expect(Number.isNaN(Date.parse(exported.project.created_at))).toBe(false);
  });

  it('ergaenzt fehlende Felder aus den Standardwerten', () => {
    const restored = parseProjectFile(
      JSON.stringify({ schema_version: '1.0', plate: { width_mm: 120 } }),
    );
    expect(restored.plate.width_mm).toBe(120);
    expect(restored.plate.height_mm).toBe(400);
    expect(restored.tool.id).toBe('T246');
    expect(restored.carving.clearance_z_mm).toBe(1);
  });

  it('ignoriert unbekannte Felder', () => {
    const restored = parseProjectFile(
      JSON.stringify({ schema_version: '1.0', hackfeld: 'boese', plate: { hack: 1, width_mm: 50 } }),
    );
    expect('hackfeld' in restored).toBe(false);
    expect('hack' in restored.plate).toBe(false);
    expect(restored.plate.width_mm).toBe(50);
  });

  it('ergaenzt die Vereinfachungswerte aus der gewaehlten Stufe', () => {
    const restored = parseProjectFile(
      JSON.stringify({ schema_version: '1.0', simplification: { mode: 'fine' } }),
    );
    expect(restored.simplification.rdp_tolerance_mm).toBe(SIMPLIFICATION_PRESETS.fine.rdp_tolerance_mm);
    expect(restored.simplification.sample_distance_mm).toBe(0.5);
  });

  it('lehnt kaputtes JSON mit einer lesbaren Meldung ab', () => {
    expect(() => parseProjectFile('{nicht wirklich json')).toThrow(ProjectFileError);
    try {
      parseProjectFile('{');
    } catch (error) {
      expect((error as Error).message).toContain('kein gueltiges JSON');
    }
  });

  it('lehnt eine unbekannte Schemaversion ab', () => {
    expect(() => parseProjectFile(JSON.stringify({ schema_version: '2.0' }))).toThrow(
      /schema_version/,
    );
  });

  it('lehnt eine unbekannte Vereinfachungsstufe ab', () => {
    expect(() =>
      parseProjectFile(JSON.stringify({ schema_version: '1.0', simplification: { mode: 'turbo' } })),
    ).toThrow(/Vereinfachungsstufe/);
  });

  it('lehnt Nicht-Objekte ab', () => {
    expect(() => parseProjectFile('[1, 2, 3]')).toThrow(ProjectFileError);
    expect(() => migrateProject('text')).toThrow(ProjectFileError);
  });

  it('nimmt eine Datei ohne Versionsangabe an', () => {
    expect(migrateProject({ project: { name: 'x' } }).schema_version).toBe(SCHEMA_VERSION);
  });
});

describe('applySimplificationMode', () => {
  it('uebernimmt die Vorbelegungen der neuen Stufe', () => {
    const updated = applySimplificationMode(defaultConfig(), 'catia_normal');
    expect(updated.simplification.mode).toBe('catia_normal');
    expect(updated.simplification.rdp_tolerance_mm).toBe(0.08);
    expect(updated.simplification.sample_distance_mm).toBe(1);
  });

  it('laesst den Rest der Konfiguration unberuehrt', () => {
    const original = defaultConfig();
    const updated = applySimplificationMode(original, 'fine');
    expect(updated.plate).toEqual(original.plate);
    expect(original.simplification.mode).toBe('catia_strong');
  });
});

describe('downloadFilename', () => {
  it('entfernt gefaehrliche Zeichen', () => {
    const config = defaultConfig();
    config.project.name = '../../etc/passwd';
    expect(downloadFilename(config, '.json')).toBe('etc-passwd.json');
  });

  it('faellt auf einen Standardnamen zurueck', () => {
    const config = defaultConfig();
    config.project.name = '///';
    expect(downloadFilename(config, '.step')).toBe('projekt.step');
  });
});
