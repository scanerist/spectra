import { Player } from "../audio/player";
import { createApi } from "../contract/api";
import { mountLoading } from "../screens/loading";
import { mountMain } from "../screens/main";
import { mountStart } from "../screens/start";
import { createDissolve } from "./dissolve";
import { element } from "./dom";
import { clockText } from "./format";
import { messageFor } from "./messages";
import { ROUTES, type Route, startRouter } from "./router";
import { type LoadedTrack, loadTrack } from "./session";

const MAX_FRAME_DT_S = 0.1;

export function startApp(root: Document): void {
  const api = createApi(
    (input, init) => fetch(input, init),
    (url) => new EventSource(url),
  );
  let player: Player | null = null;
  let track: LoadedTrack<AudioBuffer> | null = null;
  let loading = false;
  let current: Route | null = null;

  const ensurePlayer = (): Player => {
    player ??= new Player(new AudioContext());
    void player.wake();
    return player;
  };
  const timeS = () => player?.timeS() ?? 0;

  const sections = Object.fromEntries(
    ROUTES.map((route) => [route, element(root, `#s-${route}`, HTMLElement)]),
  ) as Record<Route, HTMLElement>;
  const home = element(root, "#home", HTMLAnchorElement);
  const back = element(root, "#back", HTMLAnchorElement);
  const clock = element(root, "#clock", HTMLSpanElement);
  const play = element(root, "#play", HTMLButtonElement);
  const repo = element(root, "#repo", HTMLAnchorElement);
  const unmute = element(root, "#unmute", HTMLButtonElement);
  const repositoryUrl = import.meta.env.VITE_REPOSITORY_URL ?? "";
  repo.href = repositoryUrl;

  const start = mountStart(root, (file) => void open(file), ensurePlayer);
  const loadingScreen = mountLoading(root);
  const main = mountMain(root, (seekS) => player?.seek(seekS), timeS);

  const show = (route: Route) => {
    current = route;
    for (const name of ROUTES) {
      sections[name].hidden = name !== route;
    }
    const live = track !== null && (route === "main" || route === "analysis");
    clock.hidden = !live;
    play.hidden = !live;
    back.hidden = route !== "analysis";
    repo.hidden = route !== "start" || repositoryUrl === "";
  };
  const dissolve = createDissolve(
    element(root, "#dissolve", HTMLCanvasElement),
    matchMedia("(prefers-reduced-motion: reduce)").matches,
    Math.random,
  );
  const router = startRouter(
    () => ({ trackLoaded: track !== null, loading }),
    (route) => dissolve(() => show(route)),
  );

  async function open(file: File): Promise<void> {
    start.showError(null);
    const audio = ensurePlayer();
    loading = true;
    loadingScreen.set(0, "");
    router.go("loading");
    try {
      const loaded = await loadTrack(
        file,
        { api, decode: (data) => audio.decode(data) },
        (share, label) => loadingScreen.set(share, label),
      );
      audio.play(loaded.audio);
      track = loaded;
      main.enter(loaded);
      loading = false;
      router.go("main", { replace: true });
    } catch (error) {
      loading = false;
      router.go(track === null ? "start" : "main", { replace: true });
      start.showError(messageFor(error));
    }
  }

  play.addEventListener("click", () => void player?.toggle());
  unmute.addEventListener("click", () => void player?.resumeAfterBlock());
  home.addEventListener("click", () => ensurePlayer());

  let lastClockS: number | null = null;
  const frame = (nowMs: number) => {
    const clockS = nowMs / 1000;
    const dtS = Math.min(MAX_FRAME_DT_S, clockS - (lastClockS ?? clockS));
    lastClockS = clockS;
    const running = player?.running ?? false;
    const moment = { timeS: timeS(), clockS, dtS, running };
    if (current === "start") {
      start.draw(clockS);
    }
    if (track !== null && (current === "main" || current === "analysis")) {
      clock.textContent = `${clockText(moment.timeS)} / ${clockText(track.info.durationS)}`;
      play.textContent = running ? "❚❚" : "▶";
      play.setAttribute("aria-label", running ? "Пауза" : "Продолжить");
      unmute.hidden = running || (player?.pausedByUser ?? true);
    }
    if (current === "main") {
      main.draw(moment);
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}
