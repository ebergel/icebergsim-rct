// Quick two-arm trial simulation (SPEC §17.1): enter sample size, allocation, risks,
// alpha and simulation count; get power, effect measures, and per-replicate plots.

import { useState } from "react";
import { api, ApiValidationError } from "../api";
import { NumberField } from "../components/NumberField";
import { ResultPlots } from "../components/ResultPlots";
import { SummaryCards } from "../components/SummaryCards";
import {
  buildDefinition,
  DEFAULT_FORM,
  mapErrorsToFields,
  type MappedErrors,
  type QuickTrialForm,
} from "../lib/definition";
import type { SimulationResponse } from "../types";

const NO_ERRORS: MappedErrors = { fields: {}, general: [] };

export function QuickTrial() {
  const [form, setForm] = useState<QuickTrialForm>(DEFAULT_FORM);
  const [includeTypeI, setIncludeTypeI] = useState(false);
  const [result, setResult] = useState<SimulationResponse | null>(null);
  const [errors, setErrors] = useState<MappedErrors>(NO_ERRORS);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const set = <K extends keyof QuickTrialForm>(key: K) => (value: QuickTrialForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  async function run() {
    setRunning(true);
    setErrors(NO_ERRORS);
    setFailure(null);
    try {
      const response = await api.simulate(buildDefinition(form), {
        includeTypeIError: includeTypeI,
      });
      setResult(response);
    } catch (error) {
      setResult(null);
      if (error instanceof ApiValidationError) {
        setErrors(mapErrorsToFields(error.errors));
      } else {
        setFailure(error instanceof Error ? error.message : String(error));
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <section>
      <form
        className="controls"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
      >
        <fieldset>
          <legend>Design</legend>
          <NumberField
            label="Total sample size"
            value={form.totalN}
            onChange={(v) => set("totalN")(v ?? 0)}
            min={2}
            step={2}
            error={errors.fields.totalN}
          />
          <NumberField
            label="Intervention fraction"
            value={form.interventionFraction}
            onChange={(v) => set("interventionFraction")(v ?? 0)}
            min={0}
            max={1}
            step={0.05}
            error={errors.fields.interventionFraction}
          />
          <NumberField
            label="Control event risk"
            value={form.controlRisk}
            onChange={(v) => set("controlRisk")(v ?? 0)}
            min={0}
            max={1}
            step={0.01}
            error={errors.fields.controlRisk}
          />
          <NumberField
            label="Intervention event risk"
            value={form.interventionRisk}
            onChange={(v) => set("interventionRisk")(v ?? 0)}
            min={0}
            max={1}
            step={0.01}
            error={errors.fields.interventionRisk}
          />
        </fieldset>
        <fieldset>
          <legend>Analysis & simulation</legend>
          <NumberField
            label="Alpha"
            value={form.alpha}
            onChange={(v) => set("alpha")(v ?? 0)}
            min={0}
            max={1}
            step={0.01}
            error={errors.fields.alpha}
          />
          <NumberField
            label="Simulations"
            value={form.nSimulations}
            onChange={(v) => set("nSimulations")(v ?? 0)}
            min={100}
            step={100}
            error={errors.fields.nSimulations}
            hint="≥ 3000 recommended for reported output"
          />
          <NumberField
            label="Random seed"
            value={form.randomSeed}
            onChange={set("randomSeed")}
            allowEmpty
            error={errors.fields.randomSeed}
            hint="empty = non-reproducible"
          />
          <NumberField
            label="Untreated event risk"
            value={form.untreatedRisk}
            onChange={(v) => set("untreatedRisk")(v ?? 0)}
            min={0}
            max={1}
            step={0.01}
            error={errors.fields.untreatedRisk}
            hint="used only when noncompliance is modeled"
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={includeTypeI}
              onChange={(event) => setIncludeTypeI(event.target.checked)}
            />
            <span>Also estimate Type I error (null simulation)</span>
          </label>
        </fieldset>
        <button type="submit" disabled={running} data-testid="run-button">
          {running ? "Simulating…" : "Run simulation"}
        </button>
      </form>

      {errors.general.length > 0 && (
        <ul className="banner banner-error" role="alert">
          {errors.general.map((error) => (
            <li key={`${error.code}:${error.path}`}>
              <code>{error.path}</code> — {error.message}
            </li>
          ))}
        </ul>
      )}
      {failure && (
        <p className="banner banner-error" role="alert">
          {failure}
        </p>
      )}
      {result && (
        <div data-testid="results">
          <SummaryCards result={result} />
          <ResultPlots result={result} />
        </div>
      )}
    </section>
  );
}
