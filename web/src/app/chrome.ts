import type { Route } from "./router";

export interface ChromeState {
  readonly trackLoaded: boolean;
  readonly hasRepository: boolean;
}

export interface Chrome {
  readonly clock: boolean;
  readonly play: boolean;
  readonly back: boolean;
  readonly repo: boolean;
}

export function chromeFor(route: Route, state: ChromeState): Chrome {
  const live = state.trackLoaded && (route === "main" || route === "analysis");
  return {
    clock: live,
    play: live,
    back: route === "analysis" || (route === "start" && state.trackLoaded),
    repo: route === "start" && state.hasRepository,
  };
}
