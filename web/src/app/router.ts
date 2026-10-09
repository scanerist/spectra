export const ROUTES = ["start", "loading", "main", "analysis"] as const;

export type Route = (typeof ROUTES)[number];

export interface RouteState {
  readonly trackLoaded: boolean;
  readonly loading: boolean;
}

export type Resolution =
  | { readonly kind: "show"; readonly route: Route }
  | { readonly kind: "redirect"; readonly route: Route };

export function resolveRoute(hash: string, state: RouteState): Resolution {
  const name = hash.replace(/^#/, "");
  const route = ROUTES.find((known) => known === name);
  if (route === undefined) {
    return { kind: "redirect", route: "start" };
  }
  if ((route === "main" || route === "analysis") && !state.trackLoaded) {
    return { kind: "redirect", route: "start" };
  }
  if (route === "loading" && !state.loading) {
    return { kind: "redirect", route: state.trackLoaded ? "main" : "start" };
  }
  return { kind: "show", route };
}

export interface Router {
  go(route: Route, options?: { readonly replace?: boolean }): void;
  refresh(): void;
}

export function startRouter(state: () => RouteState, show: (route: Route) => void): Router {
  let current: Route | null = null;
  const go = (route: Route, options?: { readonly replace?: boolean }) => {
    if (options?.replace === true) {
      location.replace(`#${route}`);
      refresh();
    } else {
      location.hash = `#${route}`;
    }
  };
  const refresh = () => {
    const resolution = resolveRoute(location.hash, state());
    if (resolution.kind === "redirect") {
      if (location.hash !== `#${resolution.route}`) {
        location.replace(`#${resolution.route}`);
      }
      if (resolution.route === current) {
        return;
      }
    }
    if (resolution.route !== current) {
      current = resolution.route;
      show(resolution.route);
    }
  };
  window.addEventListener("hashchange", refresh);
  refresh();
  return { go, refresh };
}
