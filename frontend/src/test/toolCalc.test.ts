import { describe, expect, it } from 'vitest';

import {
  configNotices,
  depthForGrooveWidthMm,
  formatBytesFromKb,
  grooveWidthMm,
  hasBlockingError,
  reductionNotice,
  remainingThicknessMm,
} from '../lib/toolCalc';
import { defaultConfig } from '../types/project';

describe('grooveWidthMm', () => {
  it('ergibt bei 90 Grad die doppelte Tiefe', () => {
    expect(grooveWidthMm(1.2, 90)).toBeCloseTo(2.4, 6);
    expect(grooveWidthMm(0.5, 90)).toBeCloseTo(1.0, 6);
  });

  it('wird bei kleinerem Winkel schmaler', () => {
    expect(grooveWidthMm(1, 60)).toBeLessThan(grooveWidthMm(1, 90));
    expect(grooveWidthMm(1, 60)).toBeCloseTo(2 * Math.tan(Math.PI / 6), 6);
  });

  it('wird bei groesserem Winkel breiter', () => {
    expect(grooveWidthMm(1, 120)).toBeGreaterThan(grooveWidthMm(1, 90));
  });

  it('liefert NaN bei unmoeglichen Winkeln', () => {
    expect(grooveWidthMm(1, 0)).toBeNaN();
    expect(grooveWidthMm(1, 180)).toBeNaN();
  });

  it('laesst sich umkehren', () => {
    expect(depthForGrooveWidthMm(grooveWidthMm(0.8, 75), 75)).toBeCloseTo(0.8, 6);
  });
});

describe('remainingThicknessMm', () => {
  it('rechnet die Reststaerke aus', () => {
    expect(remainingThicknessMm(3, 1.2)).toBeCloseTo(1.8, 6);
  });
});

describe('configNotices', () => {
  it('meldet bei den Standardwerten keinen Fehler', () => {
    const notices = configNotices(defaultConfig());
    expect(notices.filter((n) => n.severity === 'error')).toHaveLength(0);
    expect(hasBlockingError(defaultConfig())).toBe(false);
  });

  it('warnt bei zu geringer Reststaerke', () => {
    const config = defaultConfig();
    config.carving.max_depth_mm = 2.8;
    config.carving.line_spacing_mm = 6;
    const notices = configNotices(config);
    expect(notices.some((n) => n.severity === 'warning' && n.message.includes('0.20 mm'))).toBe(true);
  });

  it('blockiert eine Tiefe groesser als die Plattenstaerke', () => {
    const config = defaultConfig();
    config.carving.max_depth_mm = 3;
    expect(hasBlockingError(config)).toBe(true);
    expect(configNotices(config).some((n) => n.message.includes('durchtrennt'))).toBe(true);
  });

  it('warnt bei ueberschneidenden Nuten', () => {
    const config = defaultConfig();
    config.carving.line_spacing_mm = 1;
    expect(configNotices(config).some((n) => n.message.includes('Nutbreite'))).toBe(true);
  });

  it('erklaert die geaenderte Nutbreite bei anderem Winkel', () => {
    const config = defaultConfig();
    config.tool.angle_deg = 60;
    const info = configNotices(config).find((n) => n.field === 'tool.angle_deg');
    expect(info?.severity).toBe('info');
    expect(info?.message).toContain('60 Grad');
  });

  it('blockiert einen zu grossen Plattenrand', () => {
    const config = defaultConfig();
    config.plate.margin_mm = 200;
    expect(hasBlockingError(config)).toBe(true);
  });

  it('warnt bei der Stufe fein', () => {
    const config = defaultConfig();
    config.simplification.mode = 'fine';
    expect(configNotices(config).some((n) => n.message.includes('Fein'))).toBe(true);
  });

  it('blockiert ein zu dickes Relief', () => {
    const config = defaultConfig();
    config.mode = 'relief';
    config.relief.height_mm = 3;
    config.relief.base_thickness_mm = 1;
    expect(hasBlockingError(config)).toBe(true);
  });

  it.each([
    ['plate.thickness_mm', (c: ReturnType<typeof defaultConfig>) => (c.plate.thickness_mm = 0)],
    ['carving.line_spacing_mm', (c: ReturnType<typeof defaultConfig>) => (c.carving.line_spacing_mm = 0)],
    ['carving.clearance_z_mm', (c: ReturnType<typeof defaultConfig>) => (c.carving.clearance_z_mm = 0)],
    ['carving.tone_threshold', (c: ReturnType<typeof defaultConfig>) => (c.carving.tone_threshold = 2)],
    ['carving.depth_gamma', (c: ReturnType<typeof defaultConfig>) => (c.carving.depth_gamma = 0)],
    ['tool.id', (c: ReturnType<typeof defaultConfig>) => (c.tool.id = '  ')],
  ])('lehnt einen ungueltigen Wert in %s ab', (_field, mutate) => {
    const config = defaultConfig();
    mutate(config);
    expect(hasBlockingError(config)).toBe(true);
  });
});

describe('reductionNotice', () => {
  it('schweigt oberhalb der Abnahmegrenze', () => {
    expect(reductionNotice(98)).toBeNull();
    expect(reductionNotice(85)).toBeNull();
  });

  it('warnt darunter', () => {
    const notice = reductionNotice(60);
    expect(notice?.severity).toBe('warning');
    expect(notice?.message).toContain('60.0 Prozent');
  });
});

describe('formatBytesFromKb', () => {
  it('wechselt ab 1024 KB auf MB', () => {
    expect(formatBytesFromKb(512)).toBe('512 KB');
    expect(formatBytesFromKb(2048)).toBe('2.0 MB');
  });
});
