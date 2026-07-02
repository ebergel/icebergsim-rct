// Sample size and power planning (SPEC §17.3): enter risks, alpha, desired power and
// allocation; get the formula sample size, then a simulated power curve around it.
// All numbers rendered here come from the server verbatim.

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
  powerCurveSizes,
  ratioToInterventionFraction,
  type ImperfectionForm,
  type QuickTrialForm,
} from "../lib/definition";
import { fmt, fmtPercent } from "../lib/format";
import type { ApiError, PowerCurveResponse, SampleSizeResponse } from "../types";

type Alternative = "two_sided" | "superiority_one_sided" | "noninferiority_one_sided";

interface PlanForm {
  controlRisk: number;
  interventionRisk: number;
  alpha: number;
  power: number;
  ratio: number; // allocation ratio intervention : control
  alternative: Alternative;
  nSimulations: number;
  randomSeed: number | null;
}

const DEFAULT_PLAN: PlanForm = {
  controlRisk: DEFAULT_FORM.controlRisk,
  interventionRisk: DEFAULT_FORM.interventionRisk,
  alpha: DEFAULT_FORM.alpha,
  power: 0.8,
  ratio: 1,
  alternative: "two_sided",
  nSimulations: 2000,
  randomSeed: 12345,
};

// Page-local map from /api/sample-size/two-arm error paths to form fields. This endpoint
// speaks its own parameter names, so the shared definition-path mapper does not apply.
const SAMPLE_SIZE_PATH_TO_FIELD: [string, keyof PlanForm][] = [
  ["p_control", "controlRisk"],
  ["p_intervention", "interventionRisk"],
  ["alpha", "alpha"],
  ["power", "power"],
  ["allocation_ratio_intervention_to_control", "ratio"],
  ["alternative", "alternative"],
];

interface PlanErrors {
  fields: Partial<Record<keyof PlanForm, string>>;
  general: ApiError[];
}

const NO_ERRORS: PlanErrors = { fields: {}, general: [] };

function mapSampleSizeErrors(errors: ApiError[]): PlanErrors {
  const fields: PlanErrors["fields"] = {};
  const general: ApiError[] = [];
  for (const error of errors) {
    const match = SAMPLE_SIZE_PATH_TO_FIELD.find(([prefix]) => error.path.startsWith(prefix));
    if (match && fields[match[1]] === undefined) {
      fields[match[1]] = error.message;
    } else if (!match) {
      general.push(error);
    }
  }
  return { fields, general };
}

export function SampleSizePower() {
  const [form, setForm] = useState<PlanForm>(DEFAULT_PLAN);
  // Snapshot the target power alongside the formula result so the chart's reference line
  // matches the run, not whatever the form says afterwards.
  const [plan, setPlan] = useState<{ size: SampleSizeResponse; targetPower: number } | null>(
    null,
  );
  const [curve, setCurve] = useState<PowerCurveResponse | null>(null);
  // SPEC §17.3: achieved power under ideal AND pragmatic assumptions.
  const [pragmaticEnabled, setPragmaticEnabled] = useState(false);
  const [untreatedRisk, setUntreatedRisk] = useState(DEFAULT_FORM.untreatedRisk);
  const [controlImp, setControlImp] = useState<ImperfectionForm>(IDEAL_IMPERFECTIONS);
  const [interventionImp, setInterventionImp] =
    useState<ImperfectionForm>(IDEAL_IMPERFECTIONS);
  const [pragmaticCurve, setPragmaticCurve] = useState<PowerCurveResponse | null>(null);
  const [imperfectionErrors, setImperfectionErrors] = useState<{
    control: Partial<Record<keyof ImperfectionForm, string>>;
    intervention: Partial<Record<keyof ImperfectionForm, string>>;
  }>({ control: {}, intervention: {} });
  const [errors, setErrors] = useState<PlanErrors>(NO_ERRORS);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const set = <K extends keyof PlanForm>(key: K) => (value: PlanForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  async function run() {
    setRunning(true);
    setErrors(NO_ERRORS);
    setImperfectionErrors({ control: {}, intervention: {} });
    setFailure(null);
    try {
      // Step 1 — closed-form sample size from the engine.
      const size = await api.sampleSizeTwoArm({
        p_control: form.controlRisk,
        p_intervention: form.interventionRisk,
        alpha: form.alpha,
        power: form.power,
        alternative: form.alternative,
        allocation_ratio_intervention_to_control: form.ratio,
      });
      setPlan({ size, targetPower: form.power });
      setCurve(null);
      setPragmaticCurve(null);
      try {
        // Step 2 — simulated power at sizes bracketing the formula result, under ideal
        // and (optionally) pragmatic assumptions (SPEC §17.3).
        const base: QuickTrialForm = {
          ...DEFAULT_FORM,
          controlRisk: form.controlRisk,
          interventionRisk: form.interventionRisk,
          alpha: form.alpha,
          nSimulations: form.nSimulations,
          randomSeed: form.randomSeed,
          // Without noncompliance the untreated risk never enters the simulation;
          // with the pragmatic scenario enabled the user sets it explicitly.
          untreatedRisk: pragmaticEnabled ? untreatedRisk : form.controlRisk,
          totalN: size.n_total,
          interventionFraction: ratioToInterventionFraction(form.ratio),
        };
        const sizes = powerCurveSizes(size.n_total);
        const requests = [api.powerCurve(buildDefinition(base), sizes)];
        if (pragmaticEnabled) {
          requests.push(
            api.powerCurve(
              buildPragmaticDefinition(base, controlImp, interventionImp),
              sizes,
            ),
          );
        }
        const [ideal, pragmatic] = await Promise.all(requests);
        setCurve(ideal);
        setPragmaticCurve(pragmatic ?? null);
      } catch (error) {
        if (error instanceof ApiValidationError) {
          // Power-curve errors carry definition paths: arm imperfections first, then the
          // shared definition fields the two forms have in common; the rest to the banner.
          const imperfection = mapImperfectionErrors(error.errors);
          const mapped = mapErrorsToFields(imperfection.rest);
          setImperfectionErrors({
            control: imperfection.control,
            intervention: imperfection.intervention,
          });
          setErrors({
            fields: {
              controlRisk: mapped.fields.controlRisk,
              interventionRisk: mapped.fields.interventionRisk,
              alpha: mapped.fields.alpha,
              nSimulations: mapped.fields.nSimulations,
              randomSeed: mapped.fields.randomSeed,
            },
            general: [
              ...mapped.general,
              // Definition paths with no visible field on this page:
              ...imperfection.rest.filter((e) =>
                ["untreated_event_probability", "allocation"].some((prefix) =>
                  e.path.startsWith(prefix),
                ),
              ),
            ].filter(
              (error, index, all) =>
                all.findIndex((o) => o.code === error.code && o.path === error.path) ===
                index,
            ),
          });
        } else {
          setFailure(error instanceof Error ? error.message : String(error));
        }
      }
    } catch (error) {
      // Sample-size call failed: no power curve is attempted.
      setPlan(null);
      setCurve(null);
      if (error instanceof ApiValidationError) {
        setErrors(mapSampleSizeErrors(error.errors));
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
          <legend>Planning assumptions</legend>
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
            value={form.power}
            onChange={(v) => set("power")(v ?? 0)}
            min={0}
            max={1}
            step={0.05}
            error={errors.fields.power}
          />
          <NumberField
            label="Allocation ratio (intervention : control)"
            value={form.ratio}
            onChange={(v) => set("ratio")(v ?? 0)}
            min={0}
            step={0.25}
            error={errors.fields.ratio}
            hint="1 = equal arms"
          />
          <label className={`field${errors.fields.alternative ? " field-error" : ""}`}>
            <span className="field-label">Alternative hypothesis</span>
            <select
              value={form.alternative}
              onChange={(event) => set("alternative")(event.target.value as Alternative)}
              aria-label="Alternative hypothesis"
              aria-invalid={errors.fields.alternative ? true : undefined}
            >
              <option value="two_sided">two-sided</option>
              <option value="superiority_one_sided">superiority (one-sided)</option>
              <option value="noninferiority_one_sided">non-inferiority (one-sided)</option>
            </select>
            {errors.fields.alternative && (
              <span className="field-message" role="alert">
                {errors.fields.alternative}
              </span>
            )}
          </label>
        </fieldset>
        <fieldset>
          <legend>Simulation</legend>
          <NumberField
            label="Simulations"
            value={form.nSimulations}
            onChange={(v) => set("nSimulations")(v ?? 0)}
            min={100}
            step={100}
            error={errors.fields.nSimulations}
            hint="replicates per curve point"
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
              checked={pragmaticEnabled}
              onChange={(event) => setPragmaticEnabled(event.target.checked)}
              data-testid="pragmatic-toggle"
            />
            <span>Also simulate achieved power under pragmatic assumptions</span>
          </label>
        </fieldset>
        {pragmaticEnabled && (
          <>
            <fieldset>
              <legend>Pragmatic scenario</legend>
              <NumberField
                label="Untreated event risk"
                value={untreatedRisk}
                onChange={(v) => setUntreatedRisk(v ?? 0)}
                min={0}
                max={1}
                step={0.01}
                hint="event risk when noncompliant (neither treatment)"
              />
            </fieldset>
            <ImperfectionFieldset
              arm="Control"
              legend="Control arm imperfections"
              value={controlImp}
              onChange={setControlImp}
              errors={imperfectionErrors.control}
            />
            <ImperfectionFieldset
              arm="Intervention"
              legend="Intervention arm imperfections"
              value={interventionImp}
              onChange={setInterventionImp}
              errors={imperfectionErrors.intervention}
            />
          </>
        )}
        <button type="submit" disabled={running} data-testid="run-button">
          {running ? "Planning…" : "Run planning"}
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
      {plan && (
        <div data-testid="results">
          <div className="cards" data-testid="size-cards">
            <Card
              title="N per arm"
              value={`${plan.size.n_control} / ${plan.size.n_intervention}`}
              detail="control / intervention"
            />
            <Card
              title="Total N"
              value={String(plan.size.n_total)}
              detail={`formula size for ${fmtPercent(plan.targetPower, 0)} desired power`}
              accent
            />
            <Card
              title="Unrounded n (control)"
              value={fmt(plan.size.unrounded_n_control, 3)}
              detail="before rounding up"
            />
          </div>
          <p className="manifest" data-testid="formula">
            formula: {plan.size.formula} · allocation ratio{" "}
            {plan.size.allocation_ratio_intervention_to_control}
          </p>
          {curve && (
            <>
              <PlotlyChart
                testId="power-curve"
                data={[
                  {
                    type: "scatter",
                    mode: "lines+markers",
                    x: curve.plot.total_n,
                    y: curve.plot.power,
                    error_y: { type: "data", array: curve.plot.power_mcse, visible: true },
                    marker: { size: 7, color: "#2563eb" },
                    line: { color: "#2563eb" },
                    name: "ideal",
                  },
                  ...(pragmaticCurve
                    ? [
                        {
                          type: "scatter",
                          mode: "lines+markers",
                          x: pragmaticCurve.plot.total_n,
                          y: pragmaticCurve.plot.power,
                          error_y: {
                            type: "data",
                            array: pragmaticCurve.plot.power_mcse,
                            visible: true,
                          },
                          marker: { size: 7, color: "#dc2626" },
                          line: { color: "#dc2626", dash: "dot" },
                          name: "pragmatic",
                        },
                      ]
                    : []),
                ]}
                layout={{
                  title: { text: "Simulated power vs total sample size" },
                  xaxis: { title: { text: "total sample size" } },
                  yaxis: { title: { text: "simulated power" }, range: [0, 1] },
                  shapes: [
                    {
                      type: "line",
                      xref: "paper",
                      x0: 0,
                      x1: 1,
                      y0: plan.targetPower,
                      y1: plan.targetPower,
                      line: { color: "#dc2626", dash: "dash", width: 1.5 },
                      label: {
                        text: "target",
                        font: { color: "#dc2626", size: 11 },
                        textposition: "end",
                      },
                    },
                    {
                      type: "line",
                      yref: "paper",
                      y0: 0,
                      y1: 1,
                      x0: plan.size.n_total,
                      x1: plan.size.n_total,
                      line: { color: "#64748b", dash: "dash", width: 1.5 },
                      label: {
                        text: "formula N",
                        font: { color: "#64748b", size: 11 },
                        textangle: 0,
                        textposition: "end",
                      },
                    },
                  ],
                  showlegend: pragmaticCurve !== null,
                }}
              />
              <ul className="manifest" data-testid="power-points">
                {curve.points.map((point, index) => (
                  <li key={point.total_n}>
                    total n {point.total_n} ({point.n_control} control /{" "}
                    {point.n_intervention} intervention): ideal power{" "}
                    {fmtPercent(point.power)} ± {fmtPercent(point.power_mcse, 2)} MCSE
                    {pragmaticCurve?.points[index] &&
                      ` · pragmatic power ${fmtPercent(pragmaticCurve.points[index].power)} ± ${fmtPercent(pragmaticCurve.points[index].power_mcse, 2)} MCSE`}
                  </li>
                ))}
              </ul>
              <p className="manifest">
                seed {curve.random_seed ?? "none"} · {curve.rng_algorithm} · spec{" "}
                {curve.spec_version} · input {curve.input_hash.slice(0, 12)}…
              </p>
            </>
          )}
        </div>
      )}
    </section>
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
