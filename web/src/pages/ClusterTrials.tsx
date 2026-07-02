// Cluster trial planning (SPEC §17.5, engine §14): enter cluster counts/sizes, ICC and
// event risks; get the design-effect adjusted sample size and, concurrently, a simulated
// cluster trial comparing the three §14.4 analyses. All statistics come from the engine;
// values are rendered verbatim.

import { useState } from "react";
import { api, ApiValidationError } from "../api";
import { NumberField } from "../components/NumberField";
import { PlotlyChart } from "../components/PlotlyChart";
import {
  buildClusterDefinition,
  buildClusterPrePostDefinition,
  DEFAULT_CLUSTER_FORM,
  DEFAULT_PRE_POST,
  mapClusterErrors,
  type ClusterForm,
  type MappedClusterErrors,
  type PrePostExtras,
} from "../lib/definition";
import { fmt, fmtPercent } from "../lib/format";
import type {
  ApiError,
  ClusterPrePostResponse,
  ClusterPrePostSampleSizeResponse,
  ClusterResponse,
  ClusterSampleSizeResponse,
} from "../types";

interface PageErrors {
  fields: MappedClusterErrors["fields"];
  prePost: MappedClusterErrors["prePost"];
  general: ApiError[];
}

const NO_ERRORS: PageErrors = { fields: {}, prePost: {}, general: [] };

// The sample-size endpoint speaks bare parameter names (p_control, mean_cluster_size, …)
// rather than definition paths, so map those first; whatever remains goes through the
// shared cluster-definition mapper and, if still unmapped, to the general banner.
const SAMPLE_SIZE_PATH_TO_FIELD: [string, keyof ClusterForm][] = [
  ["p_control", "controlRisk"],
  ["p_intervention", "interventionRisk"],
  ["mean_cluster_size", "meanClusterSize"],
  ["alpha", "alpha"],
  ["power", "desiredPower"],
  ["icc", "icc"],
];

function mapPageErrors(errors: ApiError[]): PageErrors {
  const fields: PageErrors["fields"] = {};
  const rest: ApiError[] = [];
  for (const error of errors) {
    const match = SAMPLE_SIZE_PATH_TO_FIELD.find(([prefix]) => error.path.startsWith(prefix));
    if (match && fields[match[1]] === undefined) {
      fields[match[1]] = error.message;
    } else if (!match) {
      rest.push(error);
    }
  }
  const shared = mapClusterErrors(rest);
  // First message wins per field: sample-size paths were mapped first.
  return {
    fields: { ...shared.fields, ...fields },
    prePost: shared.prePost,
    general: shared.general,
  };
}

interface ClusterPlan {
  size: ClusterSampleSizeResponse;
  sim: ClusterResponse;
  // Present only when the pre/post design was enabled for the run.
  prePostSize: ClusterPrePostSampleSizeResponse | null;
  prePostSim: ClusterPrePostResponse | null;
  // Snapshot of the desired power at run time so the heading matches the run, not
  // whatever the form says afterwards.
  targetPower: number;
}

export function ClusterTrials() {
  const [form, setForm] = useState<ClusterForm>(DEFAULT_CLUSTER_FORM);
  const [prePostEnabled, setPrePostEnabled] = useState(false);
  const [prePost, setPrePost] = useState<PrePostExtras>(DEFAULT_PRE_POST);
  const [results, setResults] = useState<ClusterPlan | null>(null);
  const [errors, setErrors] = useState<PageErrors>(NO_ERRORS);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const set = <K extends keyof ClusterForm>(key: K) => (value: ClusterForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));
  const setExtra = <K extends keyof PrePostExtras>(key: K) => (value: PrePostExtras[K]) =>
    setPrePost((current) => ({ ...current, [key]: value }));

  // Poisson is fully determined by its mean; only these two families take an SD.
  const needsSd = form.sizeType === "negative_binomial" || form.sizeType === "lognormal";

  async function run() {
    setRunning(true);
    setErrors(NO_ERRORS);
    setFailure(null);
    const targetPower = form.desiredPower;
    // allSettled so that when BOTH requests fail validation, the errors merge (deduped
    // by code+path) rather than being lost to whichever rejected first (same layering
    // as TrialGoesBadly).
    const requests: [
      Promise<ClusterSampleSizeResponse>,
      Promise<ClusterResponse>,
      Promise<ClusterPrePostSampleSizeResponse> | null,
      Promise<ClusterPrePostResponse> | null,
    ] = [
      api.clusterSampleSize({
        p_control: form.controlRisk,
        p_intervention: form.interventionRisk,
        alpha: form.alpha,
        power: form.desiredPower,
        mean_cluster_size: form.meanClusterSize,
        icc: form.icc,
      }),
      api.cluster(buildClusterDefinition(form)),
      prePostEnabled
        ? api.clusterPrePostSampleSize({
            p_control: form.controlRisk,
            p_intervention: form.interventionRisk,
            alpha: form.alpha,
            power: form.desiredPower,
            mean_cluster_size: form.meanClusterSize,
            icc: form.icc,
            pre_post_correlation: prePost.prePostCorrelation,
          })
        : null,
      prePostEnabled ? api.clusterPrePost(buildClusterPrePostDefinition(form, prePost)) : null,
    ];
    const settled = await Promise.allSettled(
      requests.map((request) => request ?? Promise.resolve(null)),
    );
    const [sizeResult, simResult, prePostSizeResult, prePostSimResult] = settled;
    if (settled.every((r) => r.status === "fulfilled")) {
      setResults({
        size: (sizeResult as PromiseFulfilledResult<ClusterSampleSizeResponse>).value,
        sim: (simResult as PromiseFulfilledResult<ClusterResponse>).value,
        prePostSize: (
          prePostSizeResult as PromiseFulfilledResult<ClusterPrePostSampleSizeResponse | null>
        ).value,
        prePostSim: (
          prePostSimResult as PromiseFulfilledResult<ClusterPrePostResponse | null>
        ).value,
        targetPower,
      });
      setRunning(false);
      return;
    }
    setResults(null);
    const rejections = settled.filter(
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
      setErrors(mapPageErrors(validationErrors));
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
          <legend>Cluster design</legend>
          <NumberField
            label="Control clusters"
            value={form.controlClusters}
            onChange={(v) => set("controlClusters")(v ?? 0)}
            min={1}
            step={1}
            error={errors.fields.controlClusters}
          />
          <NumberField
            label="Intervention clusters"
            value={form.interventionClusters}
            onChange={(v) => set("interventionClusters")(v ?? 0)}
            min={1}
            step={1}
            error={errors.fields.interventionClusters}
          />
          <NumberField
            label="Mean cluster size"
            value={form.meanClusterSize}
            onChange={(v) => set("meanClusterSize")(v ?? 0)}
            min={1}
            step={1}
            error={errors.fields.meanClusterSize}
          />
          <label className={`field${errors.fields.sizeType ? " field-error" : ""}`}>
            <span className="field-label">Cluster size distribution</span>
            <select
              value={form.sizeType}
              onChange={(event) =>
                set("sizeType")(event.target.value as ClusterForm["sizeType"])
              }
              aria-label="Cluster size distribution"
              aria-invalid={errors.fields.sizeType ? true : undefined}
            >
              <option value="fixed">fixed</option>
              <option value="poisson">Poisson</option>
              <option value="negative_binomial">negative binomial</option>
              <option value="lognormal">log-normal</option>
            </select>
            {errors.fields.sizeType && (
              <span className="field-message" role="alert">
                {errors.fields.sizeType}
              </span>
            )}
          </label>
          {needsSd && (
            <NumberField
              label="Cluster size SD"
              value={form.sizeSd}
              onChange={set("sizeSd")}
              min={0}
              step={1}
              allowEmpty
              error={errors.fields.sizeSd}
              hint="required for variable sizes"
            />
          )}
          <NumberField
            label="ICC"
            value={form.icc}
            onChange={(v) => set("icc")(v ?? 0)}
            min={0}
            max={1}
            step={0.005}
            error={errors.fields.icc}
            hint="intra-cluster correlation"
          />
        </fieldset>
        <fieldset>
          <legend>Event risks</legend>
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
            label="Desired power"
            value={form.desiredPower}
            onChange={(v) => set("desiredPower")(v ?? 0)}
            min={0}
            max={1}
            step={0.05}
            error={errors.fields.desiredPower}
            hint="for the sample-size step"
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
          <label className="checkbox">
            <input
              type="checkbox"
              checked={prePostEnabled}
              onChange={(event) => setPrePostEnabled(event.target.checked)}
              data-testid="pre-post-toggle"
            />
            <span>Pre/post design: add baseline observations (SPEC §15)</span>
          </label>
        </fieldset>
        {prePostEnabled && (
          <fieldset>
            <legend>Pre/post design</legend>
            <NumberField
              label="Baseline event risk"
              value={prePost.baselineRisk}
              onChange={(v) => setExtra("baselineRisk")(v ?? 0)}
              min={0}
              max={1}
              step={0.01}
              error={errors.prePost.baselineRisk}
              hint="shared by both arms (randomized at baseline)"
            />
            <NumberField
              label="Pre/post correlation"
              value={prePost.prePostCorrelation}
              onChange={(v) => setExtra("prePostCorrelation")(v ?? 0)}
              min={0}
              max={1}
              step={0.05}
              error={errors.prePost.prePostCorrelation}
              hint="correlation of a cluster's baseline and follow-up rates"
            />
          </fieldset>
        )}
        <button type="submit" disabled={running} data-testid="run-button">
          {running ? "Planning…" : "Run cluster planning"}
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
      {results && (
        <>
          <ClusterResults
            size={results.size}
            sim={results.sim}
            targetPower={results.targetPower}
          />
          {results.prePostSize && results.prePostSim && (
            <PrePostResults
              size={results.prePostSize}
              sim={results.prePostSim}
              targetPower={results.targetPower}
            />
          )}
        </>
      )}
    </section>
  );
}

function PrePostResults({
  size,
  sim,
  targetPower,
}: {
  size: ClusterPrePostSampleSizeResponse;
  sim: ClusterPrePostResponse;
  targetPower: number;
}) {
  const { summary, manifest } = sim;
  const analyses = [
    {
      label: "Change score (post − pre), cluster-level t",
      short: "change score",
      power: summary.power_change_score,
      color: "#2563eb",
      flag: "primary (matches the §15.1 formula)",
    },
    {
      label: "Follow-up only, cluster-level t",
      short: "follow-up only",
      power: summary.power_followup_only,
      color: "#64748b",
      flag: "ignores baseline observations",
    },
  ];

  return (
    <div data-testid="pre-post-results">
      <h3>Pre/post design — sample size for {fmtPercent(targetPower, 0)} power</h3>
      <div className="cards" data-testid="pre-post-size-cards">
        <Card
          title="Clusters per arm"
          value={String(size.clusters_per_arm)}
          detail="with baseline observations"
          accent
        />
        <Card
          title="n per arm"
          value={String(size.n_per_arm)}
          detail={`unrounded ${fmt(size.n_per_arm_unrounded, 3)}`}
        />
      </div>
      <p className="manifest" data-testid="pre-post-formula">
        formula: {size.formula}
      </p>

      <h3>Pre/post simulated design</h3>
      <div className="cards" data-testid="pre-post-sim-cards">
        <Card
          title="Baseline CER / EER"
          value={`${fmtPercent(summary.mean_baseline_cer)} / ${fmtPercent(
            summary.mean_baseline_eer,
          )}`}
          detail="both arms share the baseline rate"
        />
        <Card
          title="Follow-up CER / EER"
          value={`${fmtPercent(summary.mean_followup_cer)} / ${fmtPercent(
            summary.mean_followup_eer,
          )}`}
          detail="arm effect applies at follow-up"
        />
        <Card
          title="Mean DiD"
          value={fmt(summary.mean_did, 3)}
          detail="control change − intervention change (positive = benefit)"
        />
      </div>

      <table data-testid="pre-post-analysis-table">
        <thead>
          <tr>
            <th scope="col">Analysis</th>
            <th scope="col">Simulated power</th>
            <th scope="col">Note</th>
          </tr>
        </thead>
        <tbody>
          {analyses.map((analysis) => (
            <tr key={analysis.label}>
              <th scope="row">{analysis.label}</th>
              <td>{fmtPercent(analysis.power)}</td>
              <td>{analysis.flag}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="plots">
        <PlotlyChart
          testId="pre-post-powers"
          data={[
            {
              type: "bar",
              x: analyses.map((a) => a.short),
              y: analyses.map((a) => a.power),
              marker: { color: analyses.map((a) => a.color) },
            },
          ]}
          layout={{
            title: { text: "Pre/post design: change score vs follow-up only" },
            yaxis: { title: { text: "simulated power" }, range: [0, 1] },
            showlegend: false,
          }}
        />
      </div>

      {sim.warnings.length > 0 && (
        <ul className="banner banner-warning" data-testid="pre-post-warnings">
          {sim.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      {sim.notes.length > 0 && (
        <ul className="banner banner-note" data-testid="pre-post-notes">
          {sim.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <p className="manifest">
        {manifest.n_simulations.toLocaleString()} simulations · seed{" "}
        {manifest.random_seed ?? "none"} · {manifest.rng_algorithm} · spec{" "}
        {manifest.spec_version} · input {manifest.input_hash.slice(0, 12)}…
      </p>
    </div>
  );
}

function ClusterResults({
  size,
  sim,
  targetPower,
}: Pick<ClusterPlan, "size" | "sim" | "targetPower">) {
  const { summary, manifest } = sim;
  // Same order as the engine notes: unadjusted (anti-conservative), design-effect
  // adjusted, cluster-level t-test (SPEC §14.4).
  const analyses = [
    {
      label: "Unadjusted chi-square",
      short: "unadjusted χ²",
      power: summary.power_unadjusted_chi_square,
      color: "#dc2626",
      flag: "⚠ anti-conservative",
    },
    {
      label: "Design-effect adjusted chi-square",
      short: "adjusted χ²",
      power: summary.power_adjusted_chi_square,
      color: "#2563eb",
      flag: null,
    },
    {
      label: "Cluster-level t-test",
      short: "cluster-level t",
      power: summary.power_cluster_level_difference,
      color: "#0d9488",
      flag: null,
    },
  ];

  return (
    <div data-testid="results">
      <h3>Sample size for {fmtPercent(targetPower, 0)} power</h3>
      <div className="cards" data-testid="size-cards">
        <Card
          title="Design effect"
          value={fmt(size.design_effect, 3)}
          detail="variance inflation from clustering"
        />
        <Card
          title="Cluster-adjusted n per arm"
          value={String(size.n_per_arm_cluster_adjusted)}
          detail="individuals per arm after adjustment"
        />
        <Card
          title="Clusters per arm"
          value={String(size.clusters_per_arm)}
          detail="at the assumed mean cluster size"
          accent
        />
      </div>
      <p className="manifest" data-testid="size-formula">
        formula: {size.formula} · individual n per arm (unrounded){" "}
        {fmt(size.individual_n_per_arm_unrounded, 3)} · cluster-adjusted (unrounded){" "}
        {fmt(size.cluster_adjusted_n_per_arm_unrounded, 3)}
      </p>

      <h3>Simulated design</h3>
      <div className="cards" data-testid="sim-cards">
        <Card
          title="Mean CER / EER"
          value={`${fmtPercent(summary.mean_cer)} / ${fmtPercent(summary.mean_eer)}`}
          detail="control / intervention event rates"
        />
        <Card
          title="Mean design effect"
          value={fmt(summary.mean_design_effect, 3)}
          detail="realized across simulated trials"
        />
        <Card
          title="Mean cluster-level difference"
          value={fmt(summary.mean_cluster_level_difference, 3)}
          detail="difference in cluster event proportions"
        />
      </div>

      <h3>Power by analysis method</h3>
      <table data-testid="analysis-table">
        <thead>
          <tr>
            <th scope="col">Analysis</th>
            <th scope="col">Simulated power</th>
            <th scope="col">Note</th>
          </tr>
        </thead>
        <tbody>
          {analyses.map((analysis) => (
            <tr key={analysis.label}>
              <th scope="row">{analysis.label}</th>
              <td>{fmtPercent(analysis.power)}</td>
              <td>{analysis.flag ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="plots">
        <PlotlyChart
          testId="analysis-powers"
          data={[
            {
              type: "bar",
              x: analyses.map((a) => a.short),
              y: analyses.map((a) => a.power),
              marker: { color: analyses.map((a) => a.color) },
            },
          ]}
          layout={{
            title: { text: "Simulated power by analysis method" },
            xaxis: { title: { text: "analysis method" } },
            yaxis: { title: { text: "power at the simulated design" }, range: [0, 1] },
            showlegend: false,
          }}
        />
      </div>

      {sim.notes.length > 0 && (
        <ul className="banner banner-note" data-testid="notes">
          {sim.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

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
