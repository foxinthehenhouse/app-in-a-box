/**
 * "Download my data" (GDPR Art. 15/20): fetch GET /api/v1/me/export, write it to
 * a JSON file in the cache directory and open the system share sheet, so the user
 * can save it to Files, email it, or AirDrop it. On web it downloads the file.
 *
 * The export is personal data, so nothing outlives the hand-off: the cache file
 * is deleted once the share sheet closes (or fails), and on web the blob URL is
 * revoked a moment after the download starts (revoking synchronously can cancel
 * it in some browsers).
 *
 * The server decides what's in it (every user-owned table, scoped by the verified
 * user id, rate-limited); the app only packages and hands it over.
 */
import { Platform, Share } from "react-native";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

import { analytics, startTimer } from "./analytics";
import { ApiError, exportMyData, type DataExport } from "./api";

/** `<slug>-data-2026-09-30.json`: dated, so repeated exports don't overwrite each other in Files. */
export function exportFileName(slug: string, when: Date = new Date()): string {
  return `${slug}-data-${when.toISOString().slice(0, 10)}.json`;
}

interface WebDoc {
  createElement: (tag: "a") => { href: string; download: string; click: () => void };
}
/** How long the browser gets to start the download before the blob URL is revoked. */
export const REVOKE_DELAY_MS = 60_000;

interface WebUrl {
  createObjectURL: (b: unknown) => string;
  revokeObjectURL: (u: string) => void;
}

async function handOver(data: DataExport, name: string): Promise<void> {
  if (Platform.OS === "web") {
    const g = globalThis as unknown as { document?: WebDoc; URL?: WebUrl; Blob?: new (parts: string[], o: { type: string }) => unknown };
    if (g.document && g.URL && g.Blob) {
      const url = g.URL.createObjectURL(new g.Blob([data.json], { type: "application/json" }));
      const a = g.document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      const revoke = g.URL.revokeObjectURL.bind(g.URL);
      setTimeout(() => revoke(url), REVOKE_DELAY_MS);
      return;
    }
  }
  if (await Sharing.isAvailableAsync()) {
    const file = new File(Paths.cache, name);
    file.create({ overwrite: true });
    try {
      file.write(data.json);
      await Sharing.shareAsync(file.uri, { mimeType: "application/json", UTI: "public.json", dialogTitle: name });
    } finally {
      try {
        file.delete();
      } catch {
        // already gone: the OS may purge the cache directory on its own
      }
    }
    return;
  }
  await Share.share({ message: data.json, title: name });
}

/** Fetch + hand over. Fires success AND failure analytics; rethrows for the screen's toast. */
export async function downloadMyData(slug: string): Promise<DataExport> {
  const elapsed = startTimer();
  try {
    const data = await exportMyData();
    await handOver(data, exportFileName(slug));
    analytics.dataExported({ success: true, error_code: null, duration_ms: elapsed() });
    return data;
  } catch (e) {
    analytics.dataExported({
      success: false,
      error_code: e instanceof ApiError ? `http_${e.status}` : "export_failed",
      duration_ms: elapsed(),
    });
    throw e;
  }
}
