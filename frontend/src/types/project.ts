/**
 * Typen des versionierten Projektformats.
 *
 * Gegenstueck zu backend/app/models/config.py und
 * shared/schemas/vcutting-project-1.0.schema.json. Aenderungen muessen an
 * allen drei Stellen erfolgen.
 */

export const SCHEMA_VERSION = '1.0';

export type ProcessingMode = 'v_cutting' | 'relief';
export type Orientation = 'vertical' | 'horizontal';
export type SimplificationMode = 'catia_strong' | 'catia_normal' | 'fine';
export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';

export interface ProjectMeta {
  name: string;
  created_at?: string | null;
}

export interface Plate {
  width_mm: number;
  height_mm: number;
  thickness_mm: number;
  top_z_mm: number;
  margin_mm: number;
}

export interface Tool {
  id: string;
  name: string;
  type: 'v_bit';
  angle_deg: number;
}

export interface Carving {
  max_depth_mm: number;
  line_spacing_mm: number;
  orientation: Orientation;
  path_mode: 'serpentine';
  clearance_z_mm: number;
  motif_margin_mm: number;
  tone_threshold: number;
  depth_gamma: number;
}

export interface Cleanup {
  remove_speckles: boolean;
  keep_largest_component: boolean;
  smooth_raster_edges: boolean;
  transparent_background: boolean;
  background_threshold: number;
  min_component_area_ratio: number;
}

export interface Simplification {
  mode: SimplificationMode;
  sample_distance_mm: number | null;
  smoothing_distance_mm: number | null;
  rdp_tolerance_mm: number | null;
  target_reduction_percent: number | null;
}

export interface Relief {
  height_mm: number;
  invert: boolean;
  smoothing_mm: number;
  base_thickness_mm: number;
  sample_distance_mm: number;
}

export interface Output {
  include_reference_plate: boolean;
  step: boolean;
  stl: boolean;
  preview_png: boolean;
}

export interface ProjectConfig {
  schema_version: string;
  mode: ProcessingMode;
  project: ProjectMeta;
  plate: Plate;
  tool: Tool;
  carving: Carving;
  cleanup: Cleanup;
  simplification: Simplification;
  relief: Relief;
  output: Output;
}

export interface PathMetrics {
  line_count: number;
  connector_count: number;
  raw_point_count: number;
  simplified_point_count: number;
  reduction_percent: number;
  avg_points_per_line: number;
  max_points_per_line: number;
  cut_length_mm: number;
  travel_length_mm: number;
  min_z_mm: number;
  max_z_mm: number;
  longest_connector_mm: number;
  estimated_step_size_kb: number;
  groove_width_mm: number;
  remaining_thickness_mm: number;
  motif_bbox_mm: number[];
  mm_per_pixel: number;
}

export interface Artifacts {
  project: boolean;
  cleaned_png: boolean;
  toolpath_png: boolean;
  simulation_png: boolean;
  step: boolean;
  stl: boolean;
  report: boolean;
}

export interface Job {
  job_id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  message: string;
  error: string | null;
  created_at: string;
  updated_at: string;
  config: ProjectConfig | null;
  metrics: PathMetrics | null;
  artifacts: Artifacts;
  warnings: string[];
  report_passed: boolean | null;
}

export interface CheckResult {
  name: string;
  passed: boolean;
  detail: string;
  value: number | string | boolean | number[] | null;
  expected: string | null;
}

export interface ValidationReport {
  schema_version: string;
  job_id: string;
  created_at: string;
  mode: string;
  passed: boolean;
  checks: CheckResult[];
  warnings: string[];
  disclaimer: string;
}

/** Vorbelegungen der Vereinfachungsstufen, identisch zum Backend. */
export const SIMPLIFICATION_PRESETS: Record<
  SimplificationMode,
  { sample_distance_mm: number; smoothing_distance_mm: number; rdp_tolerance_mm: number; target_reduction_percent: number }
> = {
  catia_strong: {
    sample_distance_mm: 2,
    smoothing_distance_mm: 2,
    rdp_tolerance_mm: 0.18,
    target_reduction_percent: 90,
  },
  catia_normal: {
    sample_distance_mm: 1,
    smoothing_distance_mm: 1,
    rdp_tolerance_mm: 0.08,
    target_reduction_percent: 80,
  },
  fine: {
    sample_distance_mm: 0.5,
    smoothing_distance_mm: 0.3,
    rdp_tolerance_mm: 0.03,
    target_reduction_percent: 50,
  },
};

export const SIMPLIFICATION_LABELS: Record<SimplificationMode, string> = {
  catia_strong: 'CATIA - stark vereinfacht',
  catia_normal: 'CATIA - normal',
  fine: 'Fein',
};

/** Ab dieser Reduktion gilt der Export als CATIA-freundlich. */
export const MIN_ACCEPTABLE_REDUCTION_PERCENT = 85;

export function defaultConfig(): ProjectConfig {
  return {
    schema_version: SCHEMA_VERSION,
    mode: 'v_cutting',
    project: { name: 'V-Cutting Projekt' },
    plate: { width_mm: 400, height_mm: 400, thickness_mm: 3, top_z_mm: 0, margin_mm: 20 },
    tool: { id: 'T246', name: 'V-Nutfraeser', type: 'v_bit', angle_deg: 90 },
    carving: {
      max_depth_mm: 1.2,
      line_spacing_mm: 2,
      orientation: 'vertical',
      path_mode: 'serpentine',
      clearance_z_mm: 1,
      motif_margin_mm: 5,
      tone_threshold: 0.055,
      depth_gamma: 1,
    },
    cleanup: {
      remove_speckles: true,
      keep_largest_component: true,
      smooth_raster_edges: true,
      transparent_background: true,
      background_threshold: 0.95,
      min_component_area_ratio: 0.0005,
    },
    simplification: { mode: 'catia_strong', ...SIMPLIFICATION_PRESETS.catia_strong },
    relief: {
      height_mm: 2,
      invert: false,
      smoothing_mm: 0.5,
      base_thickness_mm: 1,
      sample_distance_mm: 0.5,
    },
    output: { include_reference_plate: true, step: true, stl: false, preview_png: true },
  };
}
