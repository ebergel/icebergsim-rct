// Per-arm imperfection inputs (SPEC §4.2 parameters), shared by the §17.2 and §17.3 pages.

import type { ImperfectionForm } from "../lib/definition";
import { NumberField } from "./NumberField";

interface ImperfectionFieldSpec {
  key: keyof ImperfectionForm;
  label: string;
  hint?: string;
  min?: number;
  max?: number;
  step?: number;
}

export const IMPERFECTION_FIELDS: ImperfectionFieldSpec[] = [
  { key: "lossProbability", label: "loss probability", min: 0, max: 1, step: 0.01 },
  {
    key: "lostEventRiskRatio",
    label: "lost event risk ratio",
    min: 0,
    step: 0.1,
    hint: "event risk in lost participants relative to retained",
  },
  {
    key: "noncomplianceProbability",
    label: "noncompliance probability",
    min: 0,
    max: 1,
    step: 0.01,
  },
  { key: "crossoverProbability", label: "crossover probability", min: 0, max: 1, step: 0.01 },
  {
    key: "ascertainmentEventProbability",
    label: "ascertainment sensitivity",
    min: 0,
    max: 1,
    step: 0.01,
    hint: "probability a true event is detected",
  },
  {
    key: "ascertainmentFalsePositiveProbability",
    label: "false-positive ascertainment probability",
    min: 0,
    max: 1,
    step: 0.01,
  },
];

export function ImperfectionFieldset({
  arm,
  legend,
  value,
  onChange,
  errors,
}: {
  arm: "Control" | "Intervention";
  legend: string;
  value: ImperfectionForm;
  onChange: (next: ImperfectionForm) => void;
  errors: Partial<Record<keyof ImperfectionForm, string>>;
}) {
  return (
    <fieldset>
      <legend>{legend}</legend>
      {IMPERFECTION_FIELDS.map((field) => (
        <NumberField
          key={field.key}
          label={`${arm} ${field.label}`}
          value={value[field.key]}
          onChange={(v) => onChange({ ...value, [field.key]: v ?? 0 })}
          min={field.min}
          max={field.max}
          step={field.step}
          error={errors[field.key]}
          hint={field.hint}
        />
      ))}
    </fieldset>
  );
}
