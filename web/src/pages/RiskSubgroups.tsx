// Risk subgroup planning (SPEC §17.4, engine §12): define subgroups by baseline risk,
// simulate the family, and show per-subgroup + aggregate operating characteristics with a
// forest plot. All statistics come from the engine and are rendered verbatim; the aggregate
// row shows "—" for n (no client-side summing).

import { useState } from "react";
import { api, ApiValidationError } from "../api";
import { NumberField } from "../components/NumberField";
import { PlotlyChart } from "../components/PlotlyChart";
import {
  buildSubgroupFamily,
  DEFAULT_SUBGROUP_ROWS,
  DEFAULT_SUBGROUP_SHARED,
  mapSubgroupErrors,
  type MappedSubgroupErrors,
  type SubgroupRowForm,
  type SubgroupSharedForm,
} from "../lib/definition";
import { fmt, fmtCi, fmtPercent } from "../lib/format";
import type { ForestRowT, SubgroupsResponse, Summary } from "../types";

const NO_ERRORS: MappedSubgroupErrors = { rows: {}, general: [] };

const SUBGROUP_COLOR = "#2563eb";
const AGGREGATE_COLOR = "#dc2626";

// Plain text input styled like NumberField, for subgroup id/label.
function TextField({
  label,
  value,
  onChange,
  error,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
}) {
  return (
    <label className={`field${error ? " field-error" : ""}`}>
      <span className="field-label">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label={label}
        aria-invalid={error ? true : undefined}
      />
      {error && (
        <span className="field-message" role="alert">
          {error}
        </span>
      )}
    </label>
  );
}

// One CI segment + one marker per forest row, both built directly from server values.
// No client arithmetic: the segment endpoints ARE rr_low/rr_high and the marker IS rr.
function forestTraces(rows: ForestRowT[]): unknown[] {
  const traces: unknown[] = [];
  for (const row of rows) {
    const color = row.is_aggregate ? AGGREGATE_COLOR : SUBGROUP_COLOR;
    if (row.rr_low !== null && row.rr_high !== null) {
      traces.push({
        type: "scatter",
        mode: "lines",
        x: [row.rr_low, row.rr_high],
        y: [row.label, row.label],
        line: { color, width: 2 },
        hoverinfo: "skip",
        showlegend: false,
      });
    }
    if (row.rr !== null) {
      traces.push({
        type: "scatter",
        mode: "markers",
        x: [row.rr],
        y: [row.label],
        marker: {
          color,
          size: row.is_aggregate ? 12 : 9,
          symbol: row.is_aggregate ? "diamond" : "circle",
        },
        name: row.label,
        showlegend: false,
      });
    }
  }
  return traces;
}

export function RiskSubgroups() {
  const [rows, setRows] = useState<SubgroupRowForm[]>(DEFAULT_SUBGROUP_ROWS);
  const [shared, setShared] = useState<SubgroupSharedForm>(DEFAULT_SUBGROUP_SHARED);
  const [results, setResults] = useState<SubgroupsResponse | null>(null);
  const [errors, setErrors] = useState<MappedSubgroupErrors>(NO_ERRORS);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const setSharedField =
    <K extends keyof SubgroupSharedForm>(key: K) =>
    (value: SubgroupSharedForm[K]) =>
      setShared((current) => ({ ...current, [key]: value }));

  const updateRow = (index: number, patch: Partial<SubgroupRowForm>) =>
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );

  const addRow = () => {
    setRows((current) => {
      // Unique against existing ids, not just the current count, so add/remove
      // sequences never regenerate a duplicate id.
      let suffix = current.length + 1;
      while (current.some((row) => row.id === `subgroup_${suffix}`)) suffix += 1;
      return [
        ...current,
        {
          id: `subgroup_${suffix}`,
          label: "",
          totalN: 200,
          controlRisk: 0.2,
          interventionRisk: 0.1,
        },
      ];
    });
    // Row-indexed error highlights are stale once indices shift.
    setErrors(NO_ERRORS);
  };

  const removeRow = (index: number) => {
    setRows((current) => current.filter((_, i) => i !== index));
    setErrors(NO_ERRORS);
  };

  async function run() {
    setRunning(true);
    setErrors(NO_ERRORS);
    setFailure(null);
    try {
      const response = await api.subgroups(buildSubgroupFamily(shared, rows));
      setResults(response);
    } catch (error) {
      setResults(null);
      if (error instanceof ApiValidationError) {
        setErrors(mapSubgroupErrors(error.errors));
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
        {rows.map((row, index) => {
          const rowErrors = errors.rows[index] ?? {};
          return (
            <fieldset key={index}>
              <legend>Subgroup {index + 1}</legend>
              <TextField
                label={`Subgroup ${index + 1} id`}
                value={row.id}
                onChange={(v) => updateRow(index, { id: v })}
                error={rowErrors.id}
              />
              <TextField
                label={`Subgroup ${index + 1} label`}
                value={row.label}
                onChange={(v) => updateRow(index, { label: v })}
                error={rowErrors.label}
              />
              <NumberField
                label={`Subgroup ${index + 1} total N`}
                value={row.totalN}
                onChange={(v) => updateRow(index, { totalN: v ?? 0 })}
                min={2}
                step={2}
                error={rowErrors.totalN}
              />
              <NumberField
                label={`Subgroup ${index + 1} control risk`}
                value={row.controlRisk}
                onChange={(v) => updateRow(index, { controlRisk: v ?? 0 })}
                min={0}
                max={1}
                step={0.01}
                error={rowErrors.controlRisk}
              />
              <NumberField
                label={`Subgroup ${index + 1} intervention risk`}
                value={row.interventionRisk}
                onChange={(v) => updateRow(index, { interventionRisk: v ?? 0 })}
                min={0}
                max={1}
                step={0.01}
                error={rowErrors.interventionRisk}
              />
              <button
                type="button"
                onClick={() => removeRow(index)}
                disabled={rows.length === 1}
                aria-label={`Remove subgroup ${index + 1}`}
              >
                Remove
              </button>
            </fieldset>
          );
        })}
        <button type="button" onClick={addRow} data-testid="add-subgroup">
          Add subgroup
        </button>
        <fieldset>
          <legend>Shared analysis &amp; simulation</legend>
          <NumberField
            label="Alpha"
            value={shared.alpha}
            onChange={(v) => setSharedField("alpha")(v ?? 0)}
            min={0}
            max={1}
            step={0.01}
          />
          <NumberField
            label="Simulations"
            value={shared.nSimulations}
            onChange={(v) => setSharedField("nSimulations")(v ?? 0)}
            min={100}
            step={100}
            hint="shared by every subgroup (SPEC §12.1)"
          />
          <NumberField
            label="Random seed"
            value={shared.randomSeed}
            onChange={setSharedField("randomSeed")}
            allowEmpty
            hint="shared by every subgroup (SPEC §12.1); empty = non-reproducible"
          />
          <NumberField
            label="Untreated event risk"
            value={shared.untreatedRisk}
            onChange={(v) => setSharedField("untreatedRisk")(v ?? 0)}
            min={0}
            max={1}
            step={0.01}
            hint="used only when noncompliance is modeled"
          />
          <p className="muted">
            SPEC §12.1: every subgroup trial runs with the same number of simulations and
            the same random seed policy.
          </p>
        </fieldset>
        <button type="submit" disabled={running} data-testid="run-button">
          {running ? "Simulating…" : "Run subgroup planning"}
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
      {results && <Results response={results} />}
    </section>
  );
}

function summaryCells(summary: Summary) {
  return [
    fmtPercent(summary.power),
    fmtPercent(summary.mean_cer),
    fmtPercent(summary.mean_eer),
    `${fmt(summary.mean_arr)} ${fmtCi(summary.ci95_arr_empirical)}`,
    `${fmt(summary.mean_rr)} ${fmtCi(summary.ci95_rr_empirical)}`,
    fmt(summary.mean_rrr),
  ];
}

function Results({ response }: { response: SubgroupsResponse }) {
  const aggregateCells = summaryCells(response.aggregate.summary);

  return (
    <div data-testid="results">
      <table data-testid="subgroup-table">
        <thead>
          <tr>
            <th scope="col">Subgroup</th>
            <th scope="col">n (control / intervention)</th>
            <th scope="col">Power</th>
            <th scope="col">Mean CER</th>
            <th scope="col">Mean EER</th>
            <th scope="col">Mean ARR [95% CI]</th>
            <th scope="col">Mean RR [95% CI]</th>
            <th scope="col">Mean RRR</th>
          </tr>
        </thead>
        <tbody>
          {response.subgroups.map((row) => (
            <tr key={row.id}>
              <th scope="row">{row.label}</th>
              <td>
                {row.n_control} / {row.n_intervention}
              </td>
              {summaryCells(row.summary).map((cell, i) => (
                <td key={i}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr data-testid="aggregate-row">
            <th scope="row">
              <strong>Aggregate (combined trial)</strong>
            </th>
            {/* No client-side summing of arm sizes: the engine reports no aggregate n. */}
            <td>—</td>
            {aggregateCells.map((cell, i) => (
              <td key={i}>
                <strong>{cell}</strong>
              </td>
            ))}
          </tr>
        </tfoot>
      </table>
      <p className="muted">
        Aggregate row computed by the engine from summed per-replicate 2×2 counts (SPEC
        §12.2), not by averaging subgroup effects.
      </p>

      <div className="plots">
        <PlotlyChart
          testId="forest"
          data={forestTraces(response.plots.forest.rows)}
          layout={{
            title: { text: "Relative risk by subgroup (forest plot)" },
            xaxis: { title: { text: "relative risk (RR, log scale)" }, type: "log" },
            yaxis: { autorange: "reversed" },
            shapes: [
              {
                type: "line",
                x0: 1,
                x1: 1,
                yref: "paper",
                y0: 0,
                y1: 1,
                line: { color: "#64748b", dash: "dash", width: 1.5 },
              },
            ],
            showlegend: false,
          }}
        />
      </div>

      {response.warnings.length > 0 && (
        <ul className="banner banner-warning" data-testid="subgroup-warnings">
          {response.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      {response.notes.length > 0 && (
        <ul className="banner banner-note" data-testid="subgroup-notes">
          {response.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <p className="manifest" data-testid="manifest">
        {response.manifest.n_simulations.toLocaleString()} simulations per subgroup · seed{" "}
        {response.manifest.random_seed ?? "none"} · {response.manifest.rng_algorithm} ·
        spec {response.manifest.spec_version} · input{" "}
        {response.manifest.input_hash.slice(0, 12)}…
      </p>
    </div>
  );
}
