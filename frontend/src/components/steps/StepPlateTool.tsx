import { formatMm, grooveWidthMm, remainingThicknessMm } from '../../lib/toolCalc';
import type { Notice } from '../../lib/toolCalc';
import type { ProjectConfig } from '../../types/project';
import { Notices } from '../Notices';
import { NumberField, TextField } from '../NumberField';

interface Props {
  config: ProjectConfig;
  update: (patch: Partial<ProjectConfig>) => void;
  notices: Notice[];
}

function noticeFor(notices: Notice[], field: string): string | undefined {
  return notices.find((notice) => notice.severity === 'error' && notice.field === field)?.message;
}

export function StepPlate({ config, update, notices }: Props) {
  const plate = config.plate;
  const set = (patch: Partial<typeof plate>) => update({ plate: { ...plate, ...patch } });

  const usableWidth = plate.width_mm - 2 * plate.margin_mm;
  const usableHeight = plate.height_mm - 2 * plate.margin_mm;

  return (
    <section className="step">
      <h2>Schritt 2: Platte</h2>
      <p className="step__lead">
        Der Nullpunkt liegt in der linken unteren Ecke. Die Plattenoberseite ist Z = 0, die
        Unterseite liegt bei minus der Plattenstaerke.
      </p>

      <div className="grid">
        <TextField
          label="Projektname"
          value={config.project.name}
          onChange={(name) => update({ project: { ...config.project, name } })}
          maxLength={120}
        />
        <NumberField
          label="Plattenbreite"
          unit="mm"
          value={plate.width_mm}
          min={1}
          step={1}
          onChange={(width_mm) => set({ width_mm })}
          error={noticeFor(notices, 'plate')}
        />
        <NumberField
          label="Plattenhoehe"
          unit="mm"
          value={plate.height_mm}
          min={1}
          step={1}
          onChange={(height_mm) => set({ height_mm })}
        />
        <NumberField
          label="Plattenstaerke"
          unit="mm"
          value={plate.thickness_mm}
          min={0.1}
          step={0.1}
          onChange={(thickness_mm) => set({ thickness_mm })}
          error={noticeFor(notices, 'plate.thickness_mm')}
        />
        <NumberField
          label="Rand zwischen Motiv und Plattenkante"
          unit="mm"
          value={plate.margin_mm}
          min={0}
          step={1}
          onChange={(margin_mm) => set({ margin_mm })}
          error={noticeFor(notices, 'plate.margin_mm')}
        />
      </div>

      <dl className="readout">
        <div>
          <dt>Nutzbare Flaeche</dt>
          <dd data-testid="usable-area">
            {usableWidth > 0 && usableHeight > 0
              ? `${usableWidth.toFixed(0)} x ${usableHeight.toFixed(0)} mm`
              : 'keine'}
          </dd>
        </div>
        <div>
          <dt>Plattenoberseite</dt>
          <dd>Z = {plate.top_z_mm} mm</dd>
        </div>
        <div>
          <dt>Plattenunterseite</dt>
          <dd>Z = {(plate.top_z_mm - plate.thickness_mm).toFixed(2)} mm</dd>
        </div>
      </dl>
    </section>
  );
}

export function StepTool({ config, update, notices }: Props) {
  const { tool, carving, plate } = config;
  const groove = grooveWidthMm(carving.max_depth_mm, tool.angle_deg);
  const grooveAt90 = grooveWidthMm(carving.max_depth_mm, 90);
  const remaining = remainingThicknessMm(plate.thickness_mm, carving.max_depth_mm);
  const relevant = notices.filter((notice) => notice.field.startsWith('tool') || notice.field.startsWith('carving'));

  return (
    <section className="step">
      <h2>Schritt 3: Werkzeug</h2>
      <p className="step__lead">
        Die Nutbreite folgt aus <code>2 x Tiefe x tan(Winkel / 2)</code>. Ein anderer Winkel
        veraendert sie sofort.
      </p>

      <div className="grid">
        <TextField
          label="Werkzeugnummer"
          value={tool.id}
          onChange={(id) => update({ tool: { ...tool, id } })}
          maxLength={32}
          error={noticeFor(notices, 'tool.id')}
        />
        <TextField
          label="Werkzeugname"
          value={tool.name}
          onChange={(name) => update({ tool: { ...tool, name } })}
          maxLength={80}
        />
        <NumberField
          label="V-Winkel"
          unit="Grad"
          value={tool.angle_deg}
          min={1}
          max={179}
          step={1}
          onChange={(angle_deg) => update({ tool: { ...tool, angle_deg } })}
          error={noticeFor(notices, 'tool.angle_deg')}
        />
        <NumberField
          label="Maximale Frästiefe"
          unit="mm"
          value={carving.max_depth_mm}
          min={0.01}
          step={0.1}
          onChange={(max_depth_mm) => update({ carving: { ...carving, max_depth_mm } })}
          error={noticeFor(notices, 'carving.max_depth_mm')}
        />
      </div>

      <dl className="readout">
        <div>
          <dt>Maximale Nutbreite</dt>
          <dd data-testid="groove-width">{Number.isFinite(groove) ? formatMm(groove) : '-'}</dd>
        </div>
        <div>
          <dt>Verbleibende Plattenstaerke</dt>
          <dd data-testid="remaining-thickness" className={remaining < 0.5 ? 'readout--alert' : undefined}>
            {formatMm(remaining)}
          </dd>
        </div>
        <div>
          <dt>Zum Vergleich bei 90 Grad</dt>
          <dd>{formatMm(grooveAt90)}</dd>
        </div>
      </dl>

      <Notices notices={relevant} />
    </section>
  );
}
