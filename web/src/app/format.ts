const SECONDS_PER_MINUTE = 60;

export function clockText(timeS: number): string {
  const wholeS = Math.max(0, Math.floor(timeS));
  const minutes = Math.floor(wholeS / SECONDS_PER_MINUTE);
  const seconds = wholeS % SECONDS_PER_MINUTE;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function bpmText(bpm: number): string {
  return bpm.toFixed(1);
}
