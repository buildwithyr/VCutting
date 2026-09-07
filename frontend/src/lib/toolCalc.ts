/**
 * Werkzeug- und Plattenberechnungen fuer die Anzeige.
 *
 * Die verbindliche Pruefung findet im Backend statt. Diese Funktionen
 * existieren, damit die Oberflaeche sofort reagiert.
 */

import type { ProjectConfig } from '../types/project';
import { MIN_ACCEPTABLE_REDUCTION_PERCENT } from '../types/project';

/** Nutbreite = 2 * Tiefe * tan(Winkel / 2) */
export function grooveWidthMm(depthMm: number, angleDeg: number): number {
  if (!Number.isFinite(depthMm) || !Number.isFinite(angleDeg)) return Number.NaN;
  if (angleDeg <= 0 || angleDeg >= 180) return Number.NaN;
  return 2 * depthMm * Math.tan((angleDeg * Math.PI) / 360);
}

/** Umkehrung: welche Tiefe erzeugt eine bestimmte Nutbreite. */
export function depthForGrooveWidthMm(widthMm: number, angleDeg: number): number {
  if (angleDeg <= 0 || angleDeg >= 180) return Number.NaN;
  return widthMm / (2 * Math.tan((angleDeg * Math.PI) / 360));
}

export function remainingThicknessMm(thicknessMm: number, maxDepthMm: number): number {
  return thicknessMm - maxDepthMm;
}

export type Severity = 'error' | 'warning' | 'info';

export interface Notice {
  severity: Severity;
  field: string;
  message: string;
}

/**
 * Alle Hinweise zur aktuellen Konfiguration.
 *
 * `error` blockiert den Export, `warning` nicht.
 */
export function configNotices(config: ProjectConfig): Notice[] {
  const notices: Notice[] = [];
  const { plate, tool, carving, simplification } = config;

  if (!(plate.width_mm > 0) || !(plate.height_mm > 0)) {
    notices.push({ severity: 'error', field: 'plate', message: 'Plattenbreite und Plattenhoehe muessen groesser als 0 sein.' });
  }
  if (!(plate.thickness_mm > 0)) {
    notices.push({ severity: 'error', field: 'plate.thickness_mm', message: 'Die Plattenstaerke muss groesser als 0 sein.' });
  }
  if (2 * plate.margin_mm >= Math.min(plate.width_mm, plate.height_mm)) {
    notices.push({
      severity: 'error',
      field: 'plate.margin_mm',
      message: 'Der Plattenrand ist zu gross, es bleibt keine nutzbare Flaeche uebrig.',
    });
  }
  if (!(tool.angle_deg > 0) || tool.angle_deg >= 180) {
    notices.push({ severity: 'error', field: 'tool.angle_deg', message: 'Der V-Winkel muss zwischen 0 und 180 Grad liegen.' });
  }
  if (!tool.id.trim()) {
    notices.push({ severity: 'error', field: 'tool.id', message: 'Die Werkzeugnummer darf nicht leer sein.' });
  }
  // Ab hier gelten die Regeln der Fräsbahn. Im Relief-Modus entsteht keine,
  // dort zaehlen stattdessen Basisstaerke und Reliefhoehe.
  if (config.mode === 'relief') {
    const total = config.relief.base_thickness_mm + config.relief.height_mm;
    if (!(config.relief.height_mm > 0) || !(config.relief.base_thickness_mm > 0)) {
      notices.push({
        severity: 'error',
        field: 'relief.height_mm',
        message: 'Reliefhoehe und Basisstaerke muessen groesser als 0 sein.',
      });
    } else if (total > plate.thickness_mm) {
      notices.push({
        severity: 'error',
        field: 'relief.height_mm',
        message: `Basisstaerke und Reliefhoehe ergeben ${total.toFixed(2)} mm und ueberschreiten die Plattenstaerke von ${plate.thickness_mm} mm.`,
      });
    }
    return notices;
  }

  if (!(carving.max_depth_mm > 0)) {
    notices.push({ severity: 'error', field: 'carving.max_depth_mm', message: 'Die maximale Frästiefe muss groesser als 0 sein.' });
  }
  if (carving.max_depth_mm >= plate.thickness_mm) {
    notices.push({
      severity: 'error',
      field: 'carving.max_depth_mm',
      message: 'Die Frästiefe erreicht oder ueberschreitet die Plattenstaerke. Die Platte wuerde durchtrennt.',
    });
  }
  if (!(carving.line_spacing_mm > 0)) {
    notices.push({ severity: 'error', field: 'carving.line_spacing_mm', message: 'Der Linienabstand muss groesser als 0 sein.' });
  }
  if (!(carving.clearance_z_mm > 0)) {
    notices.push({ severity: 'error', field: 'carving.clearance_z_mm', message: 'Die Sicherheitshoehe muss groesser als 0 sein.' });
  }
  if (carving.tone_threshold < 0 || carving.tone_threshold > 1) {
    notices.push({ severity: 'error', field: 'carving.tone_threshold', message: 'Die Tonwertschwelle liegt zwischen 0 und 1.' });
  }
  if (!(carving.depth_gamma > 0)) {
    notices.push({ severity: 'error', field: 'carving.depth_gamma', message: 'Das Tiefengamma muss groesser als 0 sein.' });
  }

  const remaining = remainingThicknessMm(plate.thickness_mm, carving.max_depth_mm);
  if (remaining > 0 && remaining < 0.5) {
    notices.push({
      severity: 'warning',
      field: 'carving.max_depth_mm',
      message: `Unter der tiefsten Nut bleiben nur ${remaining.toFixed(2)} mm. Die Platte kann brechen oder durchscheinen.`,
    });
  }

  const groove = grooveWidthMm(carving.max_depth_mm, tool.angle_deg);
  if (Number.isFinite(groove) && groove > carving.line_spacing_mm) {
    notices.push({
      severity: 'warning',
      field: 'carving.line_spacing_mm',
      message: `Die Nutbreite ${groove.toFixed(2)} mm ist groesser als der Linienabstand ${carving.line_spacing_mm} mm. Die Nuten ueberschneiden sich stark.`,
    });
  }

  if (tool.angle_deg !== 90) {
    notices.push({
      severity: 'info',
      field: 'tool.angle_deg',
      message: `Bei ${tool.angle_deg} Grad betraegt die Nutbreite ${groove.toFixed(2)} mm statt ${grooveWidthMm(carving.max_depth_mm, 90).toFixed(2)} mm bei 90 Grad.`,
    });
  }

  if (simplification.mode === 'fine') {
    notices.push({
      severity: 'warning',
      field: 'simplification.mode',
      message: 'Die Stufe "Fein" erzeugt sehr viele Stuetzpunkte. Aeltere CATIA-STEP-Uebersetzer koennen dabei sehr langsam werden.',
    });
  }

  return notices;
}

export function hasBlockingError(config: ProjectConfig): boolean {
  return configNotices(config).some((notice) => notice.severity === 'error');
}

/** Hinweis, wenn die erreichte Reduktion unter der Abnahmegrenze liegt. */
export function reductionNotice(reductionPercent: number): Notice | null {
  if (reductionPercent >= MIN_ACCEPTABLE_REDUCTION_PERCENT) return null;
  return {
    severity: 'warning',
    field: 'simplification.mode',
    message: `Nur ${reductionPercent.toFixed(1)} Prozent Punktreduktion. Empfohlen sind mindestens ${MIN_ACCEPTABLE_REDUCTION_PERCENT} Prozent. Eine staerkere Vereinfachung oder ein groesserer Linienabstand entlasten CATIA.`,
  };
}

export function formatMm(value: number, digits = 2): string {
  return `${value.toFixed(digits)} mm`;
}

export function formatBytesFromKb(kilobytes: number): string {
  if (kilobytes >= 1024) return `${(kilobytes / 1024).toFixed(1)} MB`;
  return `${kilobytes.toFixed(0)} KB`;
}
