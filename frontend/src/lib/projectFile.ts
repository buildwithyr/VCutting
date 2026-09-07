/**
 * Import und Export von Projektdateien.
 *
 * Der Import ist bewusst tolerant gegenueber fehlenden Feldern: alles, was
 * nicht in der Datei steht, kommt aus den Standardwerten. Unbekannte
 * Schemaversionen werden dagegen klar abgelehnt.
 */

import type { ProjectConfig, SimplificationMode } from '../types/project';
import { SCHEMA_VERSION, SIMPLIFICATION_PRESETS, defaultConfig } from '../types/project';

export class ProjectFileError extends Error {}

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Uebernimmt aus `patch` nur die Schluessel, die `base` bereits kennt. */
function mergeKnown<T extends object>(base: T, patch: unknown): T {
  if (!isRecord(patch)) return base;
  const result = { ...base } as Record<string, unknown>;
  for (const [key, value] of Object.entries(patch)) {
    if (!(key in result)) continue;
    const current = result[key];
    if (isRecord(current) && isRecord(value)) {
      result[key] = mergeKnown(current as object, value);
    } else if (value !== undefined) {
      result[key] = value;
    }
  }
  return result as T;
}

/**
 * Hebt aeltere Projektdateien auf die aktuelle Schemaversion.
 * Aktuell existiert nur 1.0; die Funktion ist der Einstiegspunkt fuer spaeter.
 */
export function migrateProject(raw: unknown): UnknownRecord {
  if (!isRecord(raw)) {
    throw new ProjectFileError('Die Datei enthaelt kein JSON-Objekt.');
  }
  const version = typeof raw.schema_version === 'string' ? raw.schema_version.trim() : '';
  if (!version) {
    return { ...raw, schema_version: SCHEMA_VERSION };
  }
  if (version !== SCHEMA_VERSION) {
    throw new ProjectFileError(
      `Diese Version kennt nur schema_version "${SCHEMA_VERSION}", die Datei meldet "${version}".`,
    );
  }
  return raw;
}

/** Erzeugt aus einem beliebigen Objekt eine vollstaendige Konfiguration. */
export function projectFromJson(raw: unknown): ProjectConfig {
  const migrated = migrateProject(raw);
  const merged = mergeKnown(defaultConfig(), migrated);

  // Die Vereinfachung braucht eine Sonderbehandlung: die Standardkonfiguration
  // enthaelt bereits die Werte der Stufe "catia_strong". Ein blosses Merge
  // wuerde die Vorbelegungen einer *anderen* Stufe nie sichtbar machen.
  // Massgeblich ist deshalb, was die Datei selbst angibt.
  const fileSimplification = isRecord(migrated.simplification) ? migrated.simplification : {};
  const mode = merged.simplification.mode as SimplificationMode;
  const preset = SIMPLIFICATION_PRESETS[mode];
  if (!preset) {
    throw new ProjectFileError(`Unbekannte Vereinfachungsstufe "${String(mode)}".`);
  }
  const fromFile = (key: keyof typeof preset): number => {
    const value = fileSimplification[key];
    return typeof value === 'number' ? value : preset[key];
  };
  merged.simplification = {
    mode,
    sample_distance_mm: fromFile('sample_distance_mm'),
    smoothing_distance_mm: fromFile('smoothing_distance_mm'),
    rdp_tolerance_mm: fromFile('rdp_tolerance_mm'),
    target_reduction_percent: fromFile('target_reduction_percent'),
  };

  return merged;
}

export function parseProjectFile(text: string): ProjectConfig {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new ProjectFileError(`Die Datei ist kein gueltiges JSON: ${detail}`);
  }
  return projectFromJson(raw);
}

export function projectToJson(config: ProjectConfig): string {
  return JSON.stringify(
    { ...config, project: { ...config.project, created_at: config.project.created_at ?? new Date().toISOString() } },
    null,
    2,
  );
}

/** Wechselt die Vereinfachungsstufe und uebernimmt deren Vorbelegungen. */
export function applySimplificationMode(config: ProjectConfig, mode: SimplificationMode): ProjectConfig {
  return { ...config, simplification: { mode, ...SIMPLIFICATION_PRESETS[mode] } };
}

/**
 * Dateiname aus dem Projektnamen. Gleiche Regeln wie `safe_slug` im Backend:
 * nur A-Z, a-z, 0-9, Punkt, Bindestrich und Unterstrich; mehrfache Punkte
 * werden zusammengefasst, fuehrende und schliessende Trennzeichen fallen weg.
 */
export function downloadFilename(config: ProjectConfig, suffix: string): string {
  const slug =
    config.project.name
      .trim()
      .replace(/[^A-Za-z0-9._-]+/g, '-')
      .replace(/\.{2,}/g, '.')
      .replace(/^[-._]+|[-._]+$/g, '')
      .slice(0, 64) || 'projekt';
  return `${slug}${suffix}`;
}
