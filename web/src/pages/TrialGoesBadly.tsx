// "What if the trial goes badly?" (SPEC §17.2): configure a two-arm trial plus per-arm
// imperfections, simulate the ideal and pragmatic scenarios concurrently, and compare the
// server-reported operating characteristics side by side. All statistics come from the
// engine; the only client-side arithmetic is the labeled, display-only Δ (pragmatic − ideal).

import { useState } from "react";
import { api, ApiValidationError } from "../api";
import { ImperfectionFieldset } from "../components/ImperfectionFields";
import { NumberField } from "../components/NumberField";
import { PlotlyChart } from "../components/PlotlyChart";
import {
  buildDefinition,
  buildPragmaticDefinition,
  DEFAULT_FORM,
  IDEAL_IMPERFECTIONS,
  mapErrorsToFields,
  mapImperfectionErrors,
  type ImperfectionForm,
  type MappedErrors,
  type QuickTrialForm,
} from "../lib/definition";
import { fmt, fmtPercent } from "../lib/format";
import type { ApiError, HistogramData, SimulationResponse, Summary } from "../types";

const MINUS = "−";

interface PageErrors {
  fields: MappedErrors["fields"];
  control: Partial<Record<keyof ImperfectionForm, string>>;
  intervention: Partial<Record<keyof ImperfectionForm, string>>;
  general: ApiError[];
}

const NO_ERRORS: PageErrors = { fields: {}, control: {}, intervention: {}, general: [] };

interface ScenarioPair {
  ideal: SimulationResponse;
  pragmatic: SimulationResponse;
}

// Display-only subtraction for the descriptive Δ column; no statistical test is implied.
function diff(ideal: number | null, pragmatic: number | null): number | null {
  return ideal === null || pragmatic === null ? null : pragmatic - ideal;
}

function fmtSigned(value: number | null, digits: number, suffix = ""): string {
  if (value === null) return "—";
  const sign = value < 0 ? MINUS : "+";
  return `${sign}${Math.abs(value).toFixed(digits)}${suffix}`;
}

interface RowSpec {
  label: string;
  get: (summary: Summary) => number | null;
  fmtValue: (value: number | null) => string;
  fmtDelta: (delta: number | null) => string;
}

function percentRow(label: string, get: RowSpec["get"]): RowSpec {
  return {
    label,
    get,
    fmtValue: (v) => fmtPercent(v),
    fmtDelta: (d) => fmtSigned(d === null ? null : d * 100, 1, " pts"),
  };
}

function plainRow(label: string, get: RowSpec["get"], digits = 3): RowSpec {
  return {
    label,
    get,
    fmtValue: (v) => fmt(v, digits),
    fmtDelta: (d) => fmtSigned(d, digits),
  };
}

const COMPARISON_ROWS: RowSpec[] = [
  percentRow("Power", (s) => s.power),
  percentRow("Mean CER", (s) => s.mean_cer),
  percentRow("Mean EER", (s) => s.mean_eer),
  plainRow("Mean ARR", (s) => s.mean_arr),
  plainRow("Mean RR", (s) => s.mean_rr),
  plainRow("Mean RRR", (s) => s.mean_rrr),
  plainRow("NNT", (s) => s.mean_nnt, 1),
];

// Presentation-only bin geometry, same convention as ResultPlots.tsx.
function binCenters(histogram: HistogramData): number[] {
  return histogram.counts.map(
    (_, i) => (histogram.bin_edges[i] + histogram.bin_edges[i + 1]) / 2,
  );
}

function binWidth(histogram: HistogramData): number {
  return histogram.bin_edges.length > 1
    ? histogram.bin_edges[1] - histogram.bin_edges[0]
    : 1;
}

export function TrialGoesBadly() {
  const [form, setForm] = useState<QuickTrialForm>(DEFAULT_FORM);
  const [controlImp, setControlImp] = useState<ImperfectionForm>(IDEAL_IMPERFECTIONS);
  const [interventionImp, setInterventionImp] =
    useState<ImperfectionForm>(IDEAL_IMPERFECTIONS);
  const [results, setResults] = useState<ScenarioPair | null>(null);
  const [errors, setErrors] = useState<PageErrors>(NO_ERRORS);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const set = <K extends keyof QuickTrialForm>(key: K) => (value: QuickTrialForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  async function run() {
    setRunning(true);
    setErrors(NO_ERRORS);
    setFailure(null);
    // allSettled so that when BOTH scenarios fail validation, the imperfection-path
    // errors from the pragmatic run are merged rather than lost to whichever request
    // happened to reject first.
    const [idealResult, pragmaticResult] = await Promise.allSettled([
      api.simulate(buildDefinition(form)),
      api.simulate(buildPragmaticDefinition(form, controlImp, interventionImp)),
    ]);
    if (idealResult.status === "fulfilled" && pragmaticResult.status === "fulfilled") {
      setResults({ ideal: idealResult.value, pragmatic: pragmaticResult.value });
      setRunning(false);
      return;
    }
    setResults(null);
    const rejections = [idealResult, pragmaticResult].filter(
      (r): r is PromiseRejectedResult => r.status === "rejected",
    );
    const validationErrors = rejections
      .flatMap((r) => (r.reason instanceof ApiValidationError ? r.reason.errors : []))
      .filter(
        (error, index, all) =>
          all.findIndex((o) => o.code === error.code && o.path === error.path) === index,
      );
    const otherFailures = rejections.filter(
      (r) => !(r.reason instanceof ApiValidationError),
    );
    if (validationErrors.length > 0) {
      // Arm-imperfection paths first; whatever remains is mapped to the base fields,
      // and anything still unmapped lands in the general banner (first message wins
      // on duplicates from the two scenarios).
      const imperfection = mapImperfectionErrors(validationErrors);
      const base = mapErrorsToFields(imperfection.rest);
      setErrors({
        fields: base.fields,
        control: imperfection.control,
        intervention: imperfection.intervention,
        general: base.general,
      });
    }
    if (otherFailures.length > 0) {
      const reason = otherFailures[0].reason;
      setFailure(reason instanceof Error ? reason.message : String(reason));
    }
    setRunning(false);
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
        </fieldset>
        <ImperfectionFieldset
          arm="Control"
          legend="Control arm imperfections"
          value={controlImp}
          onChange={setControlImp}
          errors={errors.control}
        />
        <ImperfectionFieldset
          arm="Intervention"
          legend="Intervention arm imperfections"
          value={interventionImp}
          onChange={setInterventionImp}
          errors={errors.intervention}
        />
        <button type="submit" disabled={running} data-testid="run-button">
          {running ? "Simulating…" : "Run both scenarios"}
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
      {results && <Comparison ideal={results.ideal} pragmatic={results.pragmatic} />}
    </section>
  );
}

function Comparison({ ideal, pragmatic }: ScenarioPair) {
  const powerDelta = diff(ideal.summary.power, pragmatic.summary.power);
  const idealHist = ideal.plots.arr_histogram;
  const pragmaticHist = pragmatic.plots.arr_histogram;

  return (
    <div data-testid="results">
      <div className="cards">
        <div className="card card-accent" data-testid="power-callout">
          <span className="card-title">Power under imperfections</span>
          <span className="card-value">
            Power: {fmtPercent(ideal.summary.power)} → {fmtPercent(pragmatic.summary.power)}{" "}
            (Δ {fmtSigned(powerDelta === null ? null : powerDelta * 100, 1, " points")})
          </span>
          <span className="card-detail">
            descriptive difference (pragmatic − ideal); both values reported by the engine
          </span>
        </div>
      </div>

      <table data-testid="comparison-table">
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col">Ideal</th>
            <th scope="col">Pragmatic</th>
            <th scope="col">Δ</th>
          </tr>
        </thead>
        <tbody>
          {COMPARISON_ROWS.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              <td>{row.fmtValue(row.get(ideal.summary))}</td>
              <td>{row.fmtValue(row.get(pragmatic.summary))}</td>
              <td>{row.fmtDelta(diff(row.get(ideal.summary), row.get(pragmatic.summary)))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        Descriptive side-by-side comparison; no statistical test between scenarios is implied.
      </p>

      <div className="plots">
        <PlotlyChart
          testId="arr-comparison"
          data={[
            {
              type: "bar",
              x: binCenters(idealHist),
              y: idealHist.counts,
              width: binWidth(idealHist),
              name: "Ideal",
              opacity: 0.6,
              marker: { color: "#2563eb" },
            },
            {
              type: "bar",
              x: binCenters(pragmaticHist),
              y: pragmaticHist.counts,
              width: binWidth(pragmaticHist),
              name: "Pragmatic",
              opacity: 0.6,
              marker: { color: "#dc2626" },
            },
          ]}
          layout={{
            title: { text: "ARR distribution — ideal vs pragmatic (overlaid)" },
            xaxis: { title: { text: "absolute risk reduction (ARR)" } },
            yaxis: { title: { text: "simulated trials" } },
            barmode: "overlay",
            bargap: 0.05,
            showlegend: true,
          }}
        />
      </div>

      {pragmatic.warnings.length > 0 && (
        <ul className="banner banner-warning" data-testid="pragmatic-warnings">
          {pragmatic.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      {pragmatic.notes.length > 0 && (
        <ul className="banner banner-note" data-testid="pragmatic-notes">
          {pragmatic.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <p className="manifest" data-testid="manifest">
        Pragmatic run: {pragmatic.manifest.n_simulations.toLocaleString()} simulations · seed{" "}
        {pragmatic.manifest.random_seed ?? "none"} · {pragmatic.manifest.rng_algorithm} ·{" "}
        {pragmatic.manifest.p_value_method} · spec {pragmatic.manifest.spec_version} · input{" "}
        {pragmatic.manifest.input_hash.slice(0, 12)}…
      </p>
    </div>
  );
}
