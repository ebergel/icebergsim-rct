// Interim stopping simulation (SPEC §11): configure a two-arm trial plus a stopping plan
// (named rule or custom thresholds), simulate, and report how often trials stop early, in
// which direction, and at which look. All statistics come from the engine; the resolved
// plan, summary proportions, and per-look data are rendered verbatim.

import { useState } from "react";
import { api, ApiValidationError } from "../api";
import { NumberField } from "../components/NumberField";
import { PlotlyChart } from "../components/PlotlyChart";
import {
  buildStoppingDefinition,
  DEFAULT_FORM,
  DEFAULT_STOPPING,
  mapErrorsToFields,
  mapStoppingErrors,
  parseNumberList,
  type MappedErrors,
  type MappedStoppingErrors,
  type QuickTrialForm,
  type StoppingForm,
} from "../lib/definition";
import { fmtPercent } from "../lib/format";
import type { ApiError, StoppingResponse } from "../types";

const DESIGN_DEFAULTS: QuickTrialForm = { ...DEFAULT_FORM, totalN: 800 };

interface PageErrors {
  fields: MappedErrors["fields"];
  stopping: MappedStoppingErrors["stopping"];
  general: ApiError[];
}

const NO_ERRORS: PageErrors = { fields: {}, stopping: {}, general: [] };

export function StoppingRules() {
  const [form, setForm] = useState<QuickTrialForm>(DESIGN_DEFAULTS);
  const [stopping, setStopping] = useState<StoppingForm>(DEFAULT_STOPPING);
  // Raw comma-separated text for the custom thresholds; the parsed array (or null when
  // unparseable/empty) is what goes into the definition.
  const [thresholdsText, setThresholdsText] = useState("");
  const [includeTypeIError, setIncludeTypeIError] = useState(false);
  const [results, setResults] = useState<StoppingResponse | null>(null);
  const [errors, setErrors] = useState<PageErrors>(NO_ERRORS);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const set = <K extends keyof QuickTrialForm>(key: K) => (value: QuickTrialForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const setStop = <K extends keyof StoppingForm>(key: K) => (value: StoppingForm[K]) =>
    setStopping((current) => ({ ...current, [key]: value }));

  async function run() {
    setRunning(true);
    setErrors(NO_ERRORS);
    setFailure(null);
    try {
      const response = await api.stopping(buildStoppingDefinition(form, stopping), {
        includeTypeIError,
      });
      setResults(response);
    } catch (error) {
      setResults(null);
      if (error instanceof ApiValidationError) {
        // Stopping-plan paths first; the rest map to the base trial fields; anything
        // still unmapped lands in the general banner (same layering as TrialGoesBadly).
        const stoppingMapped = mapStoppingErrors(error.errors);
        const base = mapErrorsToFields(stoppingMapped.rest);
        setErrors({
          fields: base.fields,
          stopping: stoppingMapped.stopping,
          general: base.general,
        });
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
        </fieldset>
        <fieldset>
          <legend>Analysis &amp; simulation</legend>
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
        </fieldset>
        <fieldset>
          <legend>Stopping plan</legend>
          <label className={`field${errors.stopping.rule ? " field-error" : ""}`}>
            <span className="field-label">Stopping rule</span>
            <select
              value={stopping.rule}
              onChange={(event) =>
                setStop("rule")(event.target.value as StoppingForm["rule"])
              }
              aria-label="Stopping rule"
              aria-invalid={errors.stopping.rule ? true : undefined}
            >
              <option value="peto">Peto (interims p&lt;0.001)</option>
              <option value="pocock">Pocock</option>
              <option value="obrien_fleming">O'Brien-Fleming</option>
              <option value="custom">Custom thresholds</option>
            </select>
            {errors.stopping.rule && (
              <span className="field-message" role="alert">
                {errors.stopping.rule}
              </span>
            )}
          </label>
          <NumberField
            label="Number of interim looks"
            value={stopping.nInterims}
            onChange={(v) => setStop("nInterims")(v ?? 0)}
            min={1}
            max={5}
            step={1}
            error={errors.stopping.nInterims}
          />
          <label className={`field${errors.stopping.stopFor ? " field-error" : ""}`}>
            <span className="field-label">Stop for</span>
            <select
              value={stopping.stopFor}
              onChange={(event) =>
                setStop("stopFor")(event.target.value as StoppingForm["stopFor"])
              }
              aria-label="Stop for"
              aria-invalid={errors.stopping.stopFor ? true : undefined}
            >
              <option value="benefit">benefit</option>
              <option value="harm">harm</option>
              <option value="benefit_or_harm">benefit or harm</option>
            </select>
            {errors.stopping.stopFor && (
              <span className="field-message" role="alert">
                {errors.stopping.stopFor}
              </span>
            )}
          </label>
          <NumberField
            label="Minimum total events"
            value={stopping.minimumTotalEvents}
            onChange={setStop("minimumTotalEvents")}
            min={0}
            step={1}
            allowEmpty
            error={errors.stopping.minimumTotalEvents}
            hint="empty = no event-count condition"
          />
          {stopping.rule === "custom" && (
            <>
              <label
                className={`field${errors.stopping.interimPThresholds ? " field-error" : ""}`}
              >
                <span className="field-label">Interim p thresholds</span>
                <input
                  type="text"
                  value={thresholdsText}
                  onChange={(event) => {
                    const text = event.target.value;
                    setThresholdsText(text);
                    setStop("interimPThresholds")(parseNumberList(text));
                  }}
                  aria-label="Interim p thresholds"
                  aria-invalid={errors.stopping.interimPThresholds ? true : undefined}
                  placeholder="e.g. 0.0001, 0.004, 0.019"
                />
                {errors.stopping.interimPThresholds ? (
                  <span className="field-message" role="alert">
                    {errors.stopping.interimPThresholds}
                  </span>
                ) : (
                  <span className="field-hint">comma-separated, one per interim look</span>
                )}
              </label>
              <NumberField
                label="Final p threshold"
                value={stopping.finalPThreshold}
                onChange={setStop("finalPThreshold")}
                min={0}
                max={1}
                step={0.001}
                allowEmpty
                error={errors.stopping.finalPThreshold}
              />
            </>
          )}
          <label className="checkbox">
            <input
              type="checkbox"
              checked={includeTypeIError}
              onChange={(event) => setIncludeTypeIError(event.target.checked)}
              data-testid="type-i-toggle"
            />
            <span>Also estimate Type I error including stops (null simulation)</span>
          </label>
        </fieldset>
        <button type="submit" disabled={running} data-testid="run-button">
          {running ? "Simulating…" : "Run stopping simulation"}
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
      {results && <StoppingResults response={results} />}
    </section>
  );
}

function StoppingResults({ response }: { response: StoppingResponse }) {
  const { plan, summary, look_sample_sizes: lookSizes, manifest } = response;
  const stopByLook = response.plots.stop_by_look;
  const finalSizes =
    lookSizes.length > 0 ? lookSizes[lookSizes.length - 1] : null;
  const lookLabels = stopByLook.looks.map(
    (look, i) => `look ${look} (${fmtPercent(stopByLook.information_fractions[i], 0)})`,
  );

  return (
    <div data-testid="results">
      {/* Resolved plan as reported by the engine, verbatim. */}
      <p className="manifest" data-testid="plan">
        resolved plan: {plan.rule} · interim p thresholds{" "}
        {plan.interim_p_thresholds.join(", ")} · final p threshold {plan.final_p_threshold}{" "}
        · information fractions{" "}
        {plan.information_fractions.map((f) => fmtPercent(f, 0)).join(", ")} · stop for{" "}
        {plan.stop_for} · minimum total events {plan.minimum_total_events ?? "none"}
      </p>

      <div className="cards" data-testid="summary-cards">
        <Card
          title="Stopped early"
          value={fmtPercent(summary.proportion_stopped_any)}
          detail="any interim look"
        />
        <Card
          title="Stopped for benefit / harm"
          value={`${fmtPercent(summary.proportion_stopped_benefit)} / ${fmtPercent(summary.proportion_stopped_harm)}`}
          detail="benefit / harm"
        />
        <Card
          title="Mean information fraction at stop"
          value={fmtPercent(summary.mean_fraction_at_stop)}
          detail="among trials that stopped early"
        />
        <Card
          title="Power incl. stops"
          value={fmtPercent(summary.final_power_including_stops)}
          detail="significant at any look or at final analysis"
          accent
        />
        {summary.type_i_error_including_stops !== null && (
          <Card
            title="Type I incl. stops"
            value={`${fmtPercent(summary.type_i_error_including_stops)} ± ${fmtPercent(summary.type_i_error_mcse, 2)}`}
            detail="null simulation, ± MCSE"
          />
        )}
      </div>

      <table data-testid="look-table">
        <thead>
          <tr>
            <th scope="col">Look</th>
            <th scope="col">Information fraction</th>
            <th scope="col">Cumulative n (control)</th>
            <th scope="col">Cumulative n (intervention)</th>
            <th scope="col">p threshold</th>
            <th scope="col">Proportion of trials</th>
          </tr>
        </thead>
        <tbody>
          {plan.interim_p_thresholds.map((threshold, i) => (
            <tr key={`look-${i + 1}`}>
              <th scope="row">look {i + 1}</th>
              <td>{fmtPercent(plan.information_fractions[i], 0)}</td>
              <td>{lookSizes[i]?.[0] ?? "—"}</td>
              <td>{lookSizes[i]?.[1] ?? "—"}</td>
              <td>{threshold}</td>
              <td>{fmtPercent(summary.proportion_stopped_by_look[i])} stopped here</td>
            </tr>
          ))}
          <tr key="final">
            <th scope="row">final</th>
            <td>100%</td>
            <td>{finalSizes?.[0] ?? "—"}</td>
            <td>{finalSizes?.[1] ?? "—"}</td>
            <td>{plan.final_p_threshold}</td>
            <td>
              {fmtPercent(stopByLook.proportion_reaching_final)} reached final analysis
            </td>
          </tr>
        </tbody>
      </table>

      <div className="plots">
        <PlotlyChart
          testId="stop-by-look"
          data={[
            {
              type: "bar",
              x: [...lookLabels, "final"],
              y: [...stopByLook.proportions, stopByLook.proportion_reaching_final],
              marker: {
                // Interim looks in the standard blue; the "reached final" bar muted.
                color: [...stopByLook.proportions.map(() => "#2563eb"), "#64748b"],
              },
            },
          ]}
          layout={{
            title: { text: "Where simulated trials stop" },
            xaxis: { title: { text: "analysis look" } },
            yaxis: { title: { text: "proportion of simulated trials" }, range: [0, 1] },
            showlegend: false,
          }}
        />
      </div>

      <p className="manifest" data-testid="manifest">
        {manifest.n_simulations.toLocaleString()} simulations · seed{" "}
        {manifest.random_seed ?? "none"} · {manifest.rng_algorithm} · spec{" "}
        {manifest.spec_version} · input {manifest.input_hash.slice(0, 12)}…
      </p>
    </div>
  );
}

function Card({
  title,
  value,
  detail,
  accent = false,
}: {
  title: string;
  value: string;
  detail: string;
  accent?: boolean;
}) {
  return (
    <div className={`card${accent ? " card-accent" : ""}`}>
      <span className="card-title">{title}</span>
      <span className="card-value">{value}</span>
      <span className="card-detail">{detail}</span>
    </div>
  );
}
