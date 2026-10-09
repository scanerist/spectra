import { ApiError, type Stage } from "../contract/api";

export class AudioDecodeError extends Error {
  override readonly name = "AudioDecodeError";
}

export class ProtocolMismatchError extends Error {
  override readonly name = "ProtocolMismatchError";
}

const SECONDS_PER_MINUTE = 60;

export const STAGE_LABELS: Readonly<Record<Stage, string>> = {
  decoding: "декодирую",
  spectrum: "декодирую",
  tempo: "ищу темп",
  structure: "ищу структуру",
};

export const READING_LABEL = "читаю файл";
export const DONE_LABEL = "готово";

export function messageFor(error: unknown): string {
  if (error instanceof AudioDecodeError) {
    return "браузер не смог воспроизвести этот файл. попробуй mp3 или wav.";
  }
  if (error instanceof ProtocolMismatchError) {
    return "spectra обновилась. обнови страницу.";
  }
  if (!(error instanceof ApiError)) {
    return "что-то сломалось. попробуй ещё раз.";
  }
  switch (error.code) {
    case "unsupported_format":
      return "это не аудиофайл. нужен mp3, wav, flac или ogg.";
    case "file_too_large":
      return "файл слишком большой или слишком длинный.";
    case "undecodable":
      return "не получилось прочитать файл. попробуй mp3 или wav.";
    case "analysis_failed":
      return "в этом файле не нашлось ритма.";
    case "rate_limited":
      return `слишком много загрузок. попробуй через ${minutes(error.retryAfterS)} мин.`;
    case "busy":
      return "сейчас разбирается много треков. попробуй через минуту.";
    case "track_not_found":
      return "трек больше не хранится. закинь его ещё раз.";
    case "unavailable":
      return "сервер не отвечает. попробуй позже.";
    default:
      return "что-то сломалось. попробуй ещё раз.";
  }
}

function minutes(retryAfterS: number | null): number {
  return Math.max(1, Math.ceil((retryAfterS ?? SECONDS_PER_MINUTE) / SECONDS_PER_MINUTE));
}
