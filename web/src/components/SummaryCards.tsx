import { fmt, fmtCi, fmtPercent } from "../lib/format";
import type { SimulationResponse } from "../types";

export function SummaryCards({ result }: { result: SimulationResponse }) {
  const { summary, manifest } = result;
  return (
    <div>
      <div className="cards" data-testid="summary-cards">
        <Card
          title="Power"
          value={fmtPercent(summary.power)}
          detail={`MCSE ±${fmtPercent(summary.power_mcse, 2)} at α = ${manifest.alpha}`}
          accent
        />
        {summary.type_i_error !== null && (
          <Card
            title="Type I error"
            value={fmtPercent(summary.type_i_error)}
            detail={`null simulation, MCSE ±${fmtPercent(summary.type_i_error_mcse, 2)}`}
          />
        )}
        <Card
          title="Event rates"
          value={`${fmtPercent(summary.mean_cer)} vs ${fmtPercent(summary.mean_eer)}`}
          detail="mean CER vs mean EER"
        />
        <Card
          title="ARR"
          value={fmt(summary.mean_arr)}
          detail={`95% empirical CI ${fmtCi(summary.ci95_arr_empirical)}`}
        />
        <Card
          title="RR / RRR"
          value={`${fmt(summary.mean_rr)} / ${fmt(summary.mean_rrr)}`}
          detail={`RR 95% empirical CI ${fmtCi(summary.ci95_rr_empirical)}`}
        />
        <Card
          title="NNT / NNH"
          value={`${fmt(summary.mean_nnt, 1)} / ${fmt(summary.mean_nnh, 1)}`}
          detail="means over replicates where defined"
        />
      </div>
      {result.warnings.length > 0 && (
        <ul className="banner banner-warning">
          {result.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      {result.notes.length > 0 && (
        <ul className="banner banner-note">
          {result.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <p className="manifest" data-testid="manifest">
        {manifest.n_simulations.toLocaleString()} simulations · seed{" "}
        {manifest.random_seed ?? "none"} · {manifest.rng_algorithm} ·{" "}
        {manifest.p_value_method} · spec {manifest.spec_version} · input{" "}
        {manifest.input_hash.slice(0, 12)}…
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
