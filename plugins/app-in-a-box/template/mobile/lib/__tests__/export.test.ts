/**
 * "Download my data": the adapter over GET /api/v1/me/export, the file hand-off,
 * and the success + failure analytics pair.
 */
import { Platform } from "react-native";

import { ApiError, toDataExport, type DataExportWire } from "../api";
import { downloadMyData, exportFileName } from "../export";

jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn() }));
jest.mock("../analytics", () => ({
  analytics: { apiFailed: jest.fn(), dataExported: jest.fn() },
  startTimer: () => () => 42,
}));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => true), shareAsync: jest.fn(async () => undefined) }));
jest.mock("expo-file-system", () => {
  class File {
    uri: string;
    written = "";
    deleted = false;
    constructor(dir: { uri: string }, name: string) {
      this.uri = `${dir.uri}/${name}`;
      files.push(this);
    }
    create() {}
    write(s: string) {
      this.written = s;
    }
    delete() {
      this.deleted = true;
    }
  }
  const files: File[] = [];
  return { File, Paths: { cache: { uri: "file:///cache" } }, __files: files };
});
jest.mock("../api", () => {
  const actual = jest.requireActual("../api");
  return { ...actual, exportMyData: jest.fn() };
});

const api = jest.requireMock("../api") as { exportMyData: jest.Mock };
const { analytics } = jest.requireMock("../analytics") as { analytics: { dataExported: jest.Mock } };
const sharing = jest.requireMock("expo-sharing") as { shareAsync: jest.Mock };
const fs = jest.requireMock("expo-file-system") as { __files: { uri: string; written: string; deleted: boolean }[] };

const WIRE: DataExportWire = {
  formatVersion: 1,
  exportedAt: "2026-09-30T10:00:00+00:00",
  userId: "u1",
  tables: { profiles: [{ id: "u1", display_name: "Sam" }], push_tokens: [], push_tickets: [{ ticket_id: "t" }, { ticket_id: "u" }] },
};

describe("toDataExport", () => {
  it("counts rows per table and keeps the full JSON for the file", () => {
    const d = toDataExport(WIRE);
    expect(d.counts).toEqual({ profiles: 1, push_tokens: 0, push_tickets: 2 });
    expect(d.userId).toBe("u1");
    expect(JSON.parse(d.json)).toEqual(WIRE);
  });

  it("tolerates a table that isn't a list", () => {
    const odd = { ...WIRE, tables: { weird: null as unknown as Record<string, unknown>[] } };
    expect(toDataExport(odd).counts).toEqual({ weird: 0 });
  });
});

it("names the file by app and date", () => {
  expect(exportFileName("penny-jar", new Date("2026-09-30T23:00:00Z"))).toBe("penny-jar-data-2026-09-30.json");
});

describe("downloadMyData", () => {
  beforeEach(() => {
    analytics.dataExported.mockClear();
    sharing.shareAsync.mockClear();
  });

  it("writes the export to a file, opens the share sheet, and records success", async () => {
    api.exportMyData.mockResolvedValue(toDataExport(WIRE));
    const d = await downloadMyData("penny-jar");
    expect(d.counts.profiles).toBe(1);
    const file = fs.__files.at(-1);
    expect(file?.uri).toMatch(/^file:\/\/\/cache\/penny-jar-data-\d{4}-\d{2}-\d{2}\.json$/);
    expect(JSON.parse(file?.written ?? "{}")).toEqual(WIRE);
    expect(sharing.shareAsync).toHaveBeenCalledWith(file?.uri, expect.objectContaining({ mimeType: "application/json" }));
    expect(analytics.dataExported).toHaveBeenCalledWith({ success: true, error_code: null, duration_ms: 42 });
  });

  it("records the failure with the HTTP status, and rethrows for the screen", async () => {
    api.exportMyData.mockRejectedValue(new ApiError("slow down", 429));
    await expect(downloadMyData("penny-jar")).rejects.toBeInstanceOf(ApiError);
    expect(sharing.shareAsync).not.toHaveBeenCalled();
    expect(analytics.dataExported).toHaveBeenCalledWith({ success: false, error_code: "http_429", duration_ms: 42 });
  });

  it("records a share-sheet failure too (never a silent success)", async () => {
    api.exportMyData.mockResolvedValue(toDataExport(WIRE));
    sharing.shareAsync.mockRejectedValueOnce(new Error("share failed"));
    await expect(downloadMyData("penny-jar")).rejects.toThrow("share failed");
    expect(analytics.dataExported).toHaveBeenCalledWith({ success: false, error_code: "export_failed", duration_ms: 42 });
  });
});

describe("cleanup", () => {
  it("deletes the cache file once the share sheet closes, and when it fails", async () => {
    api.exportMyData.mockResolvedValue(toDataExport(WIRE));
    await downloadMyData("penny-jar");
    expect(fs.__files.at(-1)?.deleted).toBe(true);

    sharing.shareAsync.mockRejectedValueOnce(new Error("share failed"));
    await expect(downloadMyData("penny-jar")).rejects.toThrow("share failed");
    expect(fs.__files.at(-1)?.deleted).toBe(true);
  });

  it("on web, revokes the download URL only after the browser has started the download", async () => {
    jest.useFakeTimers();
    const g = globalThis as unknown as Record<string, unknown>;
    const saved = { document: g.document, createObjectURL: URL.createObjectURL, revokeObjectURL: URL.revokeObjectURL };
    const click = jest.fn();
    g.document = { createElement: () => ({ href: "", download: "", click }) };
    URL.createObjectURL = jest.fn(() => "blob:export");
    const revoke = jest.fn();
    URL.revokeObjectURL = revoke;
    jest.replaceProperty(Platform, "OS", "web");
    try {
      api.exportMyData.mockResolvedValue(toDataExport(WIRE));
      await downloadMyData("penny-jar");
      expect(click).toHaveBeenCalled();
      expect(revoke).not.toHaveBeenCalled(); // revoking synchronously can cancel the download
      jest.runAllTimers();
      expect(revoke).toHaveBeenCalledWith("blob:export");
    } finally {
      jest.restoreAllMocks();
      g.document = saved.document;
      URL.createObjectURL = saved.createObjectURL;
      URL.revokeObjectURL = saved.revokeObjectURL;
      jest.useRealTimers();
    }
  });
});
