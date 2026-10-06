
// ---- Ask (recipe-ai-feature): append to mobile/lib/api.ts -------------------------------

/** Mirrors backend/routers/ask.py `AskQuestion` (POST /api/v1/ask). */
export interface AskQuestionWire {
  question: string;
}

/** Mirrors backend/routers/ask.py `AskSource` (PUT /api/v1/ask/sources/{id}). */
export interface AskSourceWire {
  title?: string;
  text: string;
}

/** Mirrors backend/routers/ask.py `AskCitation`: which of the user's notes backs the answer. */
export interface AskCitationWire {
  index: number;
  sourceId: string;
  title: string;
  snippet: string;
}

/** Mirrors backend/routers/ask.py `AskAnswer`. `found: false` means "not in your notes". */
export interface AskAnswerWire {
  found: boolean;
  answer: string | null;
  citations: AskCitationWire[];
}

/** Mirrors backend/routers/ask.py `AskSourceIndexed`. */
export interface AskSourceIndexedWire {
  sourceId: string;
  chunks: number;
}

export type AskAnswer =
  | { found: true; answer: string; citations: AskCitationWire[] }
  | { found: false };

export function toAskAnswer(w: AskAnswerWire): AskAnswer {
  return w.found && w.answer ? { found: true, answer: w.answer, citations: w.citations } : { found: false };
}

/** 429 `ai_daily_limit` and 502 `ai_unavailable` arrive as ApiError: show them honestly, with retry.
 * @public The ask screen you build calls it; the recipe ships no screen (knip). */
export async function askQuestion(question: string): Promise<AskAnswer> {
  const body: AskQuestionWire = { question };
  return toAskAnswer(await apiFetch<AskAnswerWire>("/api/v1/ask", { method: "POST", body: JSON.stringify(body) }));
}

/** @public Call it wherever a source is saved; the recipe ships no caller (knip). */
export async function indexAskSource(sourceId: string, text: string, title = ""): Promise<number> {
  const body: AskSourceWire = { title, text };
  const w = await apiFetch<AskSourceIndexedWire>(`/api/v1/ask/sources/${encodeURIComponent(sourceId)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return w.chunks;
}

/** @public Call it wherever a source is deleted; the recipe ships no caller (knip). */
export async function removeAskSource(sourceId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/ask/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
}
