export interface NumberFieldProps {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  step?: number;
  min?: number;
  max?: number;
  error?: string;
  hint?: string;
  allowEmpty?: boolean; // empty input maps to null (e.g. random seed)
}

export function NumberField({
  label,
  value,
  onChange,
  step,
  min,
  max,
  error,
  hint,
  allowEmpty = false,
}: NumberFieldProps) {
  return (
    <label className={`field${error ? " field-error" : ""}`}>
      <span className="field-label">{label}</span>
      <input
        type="number"
        value={value ?? ""}
        step={step}
        min={min}
        max={max}
        onChange={(event) => {
          const raw = event.target.value;
          if (raw === "") {
            onChange(allowEmpty ? null : 0);
            return;
          }
          const parsed = Number(raw);
          if (!Number.isNaN(parsed)) onChange(parsed);
        }}
        aria-invalid={error ? true : undefined}
        aria-label={label}
      />
      {error ? (
        <span className="field-message" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="field-hint">{hint}</span>
      ) : null}
    </label>
  );
}
