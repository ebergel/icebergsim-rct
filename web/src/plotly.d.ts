declare module "plotly.js-dist-min" {
  export interface PlotlyModule {
    react(root: HTMLElement, data: unknown[], layout?: Record<string, unknown>): Promise<void>;
    purge(root: HTMLElement): void;
  }
  const Plotly: PlotlyModule;
  export default Plotly;
}
