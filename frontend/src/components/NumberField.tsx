interface NumberFieldProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
  error?: string;
  id?: string;
  disabled?: boolean;
}

/**
 * Zahlenfeld mit Einheit und Fehlermeldung.
 *
 * Leere oder unlesbare Eingaben werden nicht stillschweigend auf 0 gesetzt;
 * der zuletzt gueltige Wert bleibt bestehen, bis eine Zahl eingegeben wird.
 */
export function NumberField({
  label,
  value,
  onChange,
  unit,
  min,
  max,
  step = 0.1,
  hint,
  error,
  id,
  disabled = false,
}: NumberFieldProps) {
  const fieldId = id ?? `field-${label.replace(/\s+/g, '-').toLowerCase()}`;
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;

  return (
    <div className={`field${error ? ' field--error' : ''}`}>
      <label htmlFor={fieldId}>
        {label}
        {unit ? <span className="field__unit"> ({unit})</span> : null}
      </label>
      <input
        id={fieldId}
        type="number"
        inputMode="decimal"
        value={Number.isFinite(value) ? value : ''}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={[hintId, errorId].filter(Boolean).join(' ') || undefined}
        onChange={(event) => {
          const parsed = Number.parseFloat(event.target.value);
          if (!Number.isNaN(parsed)) onChange(parsed);
        }}
      />
      {hint ? (
        <p className="field__hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="field__error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  id?: string;
  maxLength?: number;
}

export function TextField({ label, value, onChange, hint, error, id, maxLength }: TextFieldProps) {
  const fieldId = id ?? `field-${label.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <div className={`field${error ? ' field--error' : ''}`}>
      <label htmlFor={fieldId}>{label}</label>
      <input
        id={fieldId}
        type="text"
        value={value}
        maxLength={maxLength}
        aria-invalid={error ? true : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint ? <p className="field__hint">{hint}</p> : null}
      {error ? (
        <p className="field__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

interface SelectFieldProps<T extends string> {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  hint?: string;
  id?: string;
}

export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
  hint,
  id,
}: SelectFieldProps<T>) {
  const fieldId = id ?? `field-${label.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      <select id={fieldId} value={value} onChange={(event) => onChange(event.target.value as T)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint ? <p className="field__hint">{hint}</p> : null}
    </div>
  );
}

interface CheckFieldProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: string;
  id?: string;
}

export function CheckField({ label, checked, onChange, hint, id }: CheckFieldProps) {
  const fieldId = id ?? `check-${label.replace(/\s+/g, '-').toLowerCase()}`;
  return (
    <div className="field field--check">
      <label htmlFor={fieldId}>
        <input
          id={fieldId}
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{label}</span>
      </label>
      {hint ? <p className="field__hint">{hint}</p> : null}
    </div>
  );
}
