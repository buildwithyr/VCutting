import { applySimplificationMode } from '../../lib/projectFile';
import type { Notice } from '../../lib/toolCalc';
import type { Orientation, ProcessingMode, ProjectConfig, SimplificationMode } from '../../types/project';
import { SIMPLIFICATION_LABELS, SIMPLIFICATION_PRESETS } from '../../types/project';
import { Notices } from '../Notices';
import { CheckField, NumberField, SelectField } from '../NumberField';

interface Props {
  config: ProjectConfig;
  update: (patch: Partial<ProjectConfig>) => void;
  replace: (config: ProjectConfig) => void;
  notices: Notice[];
}

export function StepPath({ config, update, replace, notices }: Props) {
  const { carving, simplification, relief } = config;
  const preset = SIMPLIFICATION_PRESETS[simplification.mode];
  const relevant = notices.filter(
    (notice) => notice.field.startsWith('carving') || notice.field.startsWith('simplification') || notice.field.startsWith('relief'),
  );

  return (
    <section className="step">
      <h2>Schritt 4: Bahn</h2>

      <SelectField<ProcessingMode>
        label="Bearbeitungsart"
        value={config.mode}
        options={[
          { value: 'v_cutting', label: 'V-Cutting (STEP mit Fraesbahn)' },
          { value: 'relief', label: 'Relief (STL aus Hoehenkarte)' },
        ]}
        onChange={(mode) => update({ mode })}
        hint={
          config.mode === 'relief'
            ? 'Der Relief-Modus erzeugt statt einer Fraesbahn ein geschlossenes STL. Er ist Phase 2 und ersetzt den V-Cutting-Export.'
            : undefined
        }
      />

      {config.mode === 'v_cutting' ? (
        <>
          <div className="grid">
            <SelectField<Orientation>
              label="Linienrichtung"
              value={carving.orientation}
              options={[
                { value: 'vertical', label: 'Vertikal (Linien entlang Y)' },
                { value: 'horizontal', label: 'Horizontal (Linien entlang X)' },
              ]}
              onChange={(orientation) => update({ carving: { ...carving, orientation } })}
            />
            <SelectField
              label="Bahnart"
              value={carving.path_mode}
              options={[{ value: 'serpentine', label: 'Schlangenbahn' }]}
              onChange={() => undefined}
              hint="Im MVP ist nur die Schlangenbahn umgesetzt."
            />
            <NumberField
              label="Linienabstand"
              unit="mm"
              value={carving.line_spacing_mm}
              min={0.1}
              step={0.1}
              onChange={(line_spacing_mm) => update({ carving: { ...carving, line_spacing_mm } })}
            />
            <NumberField
              label="Sicherheitshoehe ueber dem Werkstueck"
              unit="mm"
              value={carving.clearance_z_mm}
              min={0.1}
              step={0.1}
              onChange={(clearance_z_mm) => update({ carving: { ...carving, clearance_z_mm } })}
              hint="Leerfahrten und Linienenden liegen auf diesem Z-Wert."
            />
            <NumberField
              label="Abstand ausserhalb der Motivkontur"
              unit="mm"
              value={carving.motif_margin_mm}
              min={0}
              step={0.5}
              onChange={(motif_margin_mm) => update({ carving: { ...carving, motif_margin_mm } })}
              hint="Die Bahn folgt der Motivkontur plus diesem Rand, nicht dem Bildrechteck."
            />
            <NumberField
              label="Tonwertschwelle"
              value={carving.tone_threshold}
              min={0}
              max={1}
              step={0.005}
              onChange={(tone_threshold) => update({ carving: { ...carving, tone_threshold } })}
              hint="Tonwerte darunter bleiben ungeschnitten."
            />
            <NumberField
              label="Tiefengamma"
              value={carving.depth_gamma}
              min={0.1}
              max={10}
              step={0.1}
              onChange={(depth_gamma) => update({ carving: { ...carving, depth_gamma } })}
              hint="Groesser als 1 macht mittlere Tonwerte flacher."
            />
          </div>

          <h3>Vereinfachung</h3>
          <SelectField<SimplificationMode>
            label="Vereinfachungsmodus"
            value={simplification.mode}
            options={(Object.keys(SIMPLIFICATION_LABELS) as SimplificationMode[]).map((mode) => ({
              value: mode,
              label: SIMPLIFICATION_LABELS[mode],
            }))}
            onChange={(mode) => replace(applySimplificationMode(config, mode))}
          />
          <dl className="readout">
            <div>
              <dt>Y-Abtastung</dt>
              <dd>{preset.sample_distance_mm} mm</dd>
            </div>
            <div>
              <dt>Tiefenglaettung</dt>
              <dd>{preset.smoothing_distance_mm} mm</dd>
            </div>
            <div>
              <dt>RDP-Toleranz</dt>
              <dd data-testid="rdp-tolerance">{preset.rdp_tolerance_mm} mm</dd>
            </div>
            <div>
              <dt>Zielreduktion</dt>
              <dd>{preset.target_reduction_percent} Prozent</dd>
            </div>
          </dl>
        </>
      ) : (
        <div className="grid">
          <NumberField
            label="Reliefhoehe"
            unit="mm"
            value={relief.height_mm}
            min={0.1}
            step={0.1}
            onChange={(height_mm) => update({ relief: { ...relief, height_mm } })}
          />
          <NumberField
            label="Basisstaerke"
            unit="mm"
            value={relief.base_thickness_mm}
            min={0.1}
            step={0.1}
            onChange={(base_thickness_mm) => update({ relief: { ...relief, base_thickness_mm } })}
          />
          <NumberField
            label="Glaettung"
            unit="mm"
            value={relief.smoothing_mm}
            min={0}
            step={0.1}
            onChange={(smoothing_mm) => update({ relief: { ...relief, smoothing_mm } })}
          />
          <NumberField
            label="Rasterabstand"
            unit="mm"
            value={relief.sample_distance_mm}
            min={0.05}
            step={0.05}
            onChange={(sample_distance_mm) => update({ relief: { ...relief, sample_distance_mm } })}
            hint="Sehr feine Raster werden serverseitig vergroebert, damit das STL handhabbar bleibt."
          />
          <CheckField
            label="Hoehe invertieren"
            checked={relief.invert}
            onChange={(invert) => update({ relief: { ...relief, invert } })}
            hint="Standard: helle Stellen liegen hoch."
          />
        </div>
      )}

      <h3>Ausgabe</h3>
      <div className="grid">
        <CheckField
          label="Referenzplatte in die Datei aufnehmen"
          checked={config.output.include_reference_plate}
          onChange={(include_reference_plate) =>
            update({ output: { ...config.output, include_reference_plate } })
          }
        />
        <CheckField
          label="STEP erzeugen"
          checked={config.output.step}
          onChange={(step) => update({ output: { ...config.output, step } })}
        />
        <CheckField
          label="STL erzeugen"
          checked={config.output.stl}
          onChange={(stl) => update({ output: { ...config.output, stl } })}
          hint="Bei V-Cutting die Referenzplatte, im Relief-Modus der Reliefkoerper."
        />
        <CheckField
          label="Vorschaubilder erzeugen"
          checked={config.output.preview_png}
          onChange={(preview_png) => update({ output: { ...config.output, preview_png } })}
        />
      </div>

      <Notices notices={relevant} />
    </section>
  );
}
