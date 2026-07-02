import { useEffect, useState } from "react";
import { api } from "./api";
import { QuickTrial } from "./pages/QuickTrial";
import { SampleSizePower } from "./pages/SampleSizePower";
import { TrialGoesBadly } from "./pages/TrialGoesBadly";

const PAGES = [
  { key: "quick", label: "Quick Trial", ready: true },
  { key: "imperfections", label: "Trial Goes Badly", ready: true },
  { key: "sample-size", label: "Sample Size & Power", ready: true },
  { key: "stopping", label: "Stopping Rules", ready: false },
  { key: "subgroups", label: "Risk Subgroups", ready: false },
  { key: "cluster", label: "Cluster Trials", ready: false },
] as const;

type PageKey = (typeof PAGES)[number]["key"];

export function App() {
  const [page, setPage] = useState<PageKey>("quick");
  const [specVersion, setSpecVersion] = useState<string>("");

  useEffect(() => {
    api
      .meta()
      .then((meta) => setSpecVersion(meta.spec_version))
      .catch(() => setSpecVersion(""));
  }, []);

  return (
    <div className="app">
      <header>
        <h1>
          ICEBERGSIM <span className="muted">v2</span>
        </h1>
        <p className="tagline">
          Clinical trial simulator — signal, noise, and sample size, first-hand.
          {specVersion && <span className="muted"> spec {specVersion}</span>}
        </p>
        <nav>
          {PAGES.map(({ key, label, ready }) => (
            <button
              key={key}
              className={page === key ? "tab tab-active" : "tab"}
              disabled={!ready}
              title={ready ? undefined : "coming soon"}
              onClick={() => setPage(key)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {page === "quick" && <QuickTrial />}
        {page === "imperfections" && <TrialGoesBadly />}
        {page === "sample-size" && <SampleSizePower />}
      </main>
      <footer>
        <p className="muted">
          Simulated operating characteristics of hypothetical designs — judgment about real
          trials belongs to trialists, statisticians, ethics committees, participants, and
          regulators.
        </p>
      </footer>
    </div>
  );
}
