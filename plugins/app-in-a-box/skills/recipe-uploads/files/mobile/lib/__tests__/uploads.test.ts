/**
 * Image uploads (recipe-uploads): the checks before a request, the PUT with progress,
 * the success + failure analytics pair, and retry resuming at the step that failed.
 */
import { act, renderHook } from "@testing-library/react-native";

import { ApiError, type Upload, type UploadTicket } from "../api";
import {
  MAX_UPLOAD_BYTES,
  UploadError,
  checkImage,
  contentTypeOf,
  pickImage,
  putFile,
  uploadErrorCode,
  uploadErrorMessage,
  useImageUpload,
} from "../uploads";

jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn() }));
jest.mock("../analytics", () => ({
  analytics: { apiFailed: jest.fn(), imageUploaded: jest.fn() },
  startTimer: () => () => 42,
}));
jest.mock("expo-image-picker", () => ({ launchImageLibraryAsync: jest.fn() }));
jest.mock("expo-file-system", () => ({
  File: class {
    uri: string;
    size = 777;
    constructor(uri: string) {
      this.uri = uri;
    }
  },
}));
jest.mock("../api", () => {
  const actual = jest.requireActual("../api");
  return { ...actual, createUpload: jest.fn(), completeUpload: jest.fn() };
});

const api = jest.requireMock("../api") as { createUpload: jest.Mock; completeUpload: jest.Mock };
const picker = jest.requireMock("expo-image-picker") as { launchImageLibraryAsync: jest.Mock };
const { analytics } = jest.requireMock("../analytics") as { analytics: { imageUploaded: jest.Mock } };

// ---- a scriptable XMLHttpRequest ------------------------------------------------------------

interface Outcome {
  status?: number;
  fail?: "network" | "timeout";
}
const outcomes: Outcome[] = [];
const sent: { method: string; url: string; body: unknown }[] = [];

class FakeXHR {
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  status = 0;
  timeout = 0;
  private method = "";
  private url = "";
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  send(body: unknown) {
    sent.push({ method: this.method, url: this.url, body });
    const o = outcomes.shift() ?? { status: 200 };
    void Promise.resolve().then(() => {
      this.upload.onprogress?.({ lengthComputable: true, loaded: 40, total: 100 });
      if (o.fail === "network") this.onerror?.();
      else if (o.fail === "timeout") this.ontimeout?.();
      else {
        this.status = o.status ?? 200;
        this.onload?.();
      }
    });
  }
}

const realXHR = globalThis.XMLHttpRequest;
beforeAll(() => {
  (globalThis as unknown as { XMLHttpRequest: unknown }).XMLHttpRequest = FakeXHR;
});
afterAll(() => {
  globalThis.XMLHttpRequest = realXHR;
});

const PHOTO = { uri: "file:///tmp/photo.jpg", mimeType: "image/jpeg", fileSize: 2048 };
const TICKET: UploadTicket = { uploadId: "u-1", signedUrl: "https://example.supabase.co/storage/v1/object/upload/sign/uploads/me/u-1?token=t" };
const UPLOAD: Upload = { id: "u-1", contentType: "image/jpeg", sizeBytes: 2048, createdAt: "2026-10-04T10:00:00Z", url: "https://cdn/u-1" };

function pickReturns(asset: Record<string, unknown> | null) {
  picker.launchImageLibraryAsync.mockResolvedValue(asset ? { canceled: false, assets: [asset] } : { canceled: true, assets: null });
}

beforeEach(() => {
  jest.clearAllMocks();
  outcomes.length = 0;
  sent.length = 0;
  api.createUpload.mockResolvedValue(TICKET);
  api.completeUpload.mockResolvedValue(UPLOAD);
  pickReturns(PHOTO);
});

// ---- pure parts ----------------------------------------------------------------------------------

describe("checks before any request", () => {
  it("reads the type from the picker, else the extension", () => {
    expect(contentTypeOf({ uri: "x.png", mimeType: "IMAGE/WEBP" })).toBe("image/webp");
    expect(contentTypeOf({ uri: "file:///a/b.HEIC?x=1", mimeType: "" })).toBe("image/heic");
    expect(contentTypeOf({ uri: "file:///a/b.gif", mimeType: "" })).toBe("");
  });

  it("refuses what the server would refuse", () => {
    expect(checkImage({ uri: "a.jpg", mimeType: "image/jpeg", sizeBytes: 10 })).toBe("image/jpeg");
    expect(() => checkImage({ uri: "a.gif", mimeType: "image/gif", sizeBytes: 10 })).toThrow("unsupported_type");
    expect(() => checkImage({ uri: "a.jpg", mimeType: "image/jpeg", sizeBytes: MAX_UPLOAD_BYTES + 1 })).toThrow("too_large");
    expect(() => checkImage({ uri: "a.jpg", mimeType: "image/jpeg", sizeBytes: 0 })).toThrow("empty_file");
  });

  it("maps failures to stable codes and kind messages", () => {
    expect(uploadErrorCode(new ApiError("x", 422))).toBe("http_422");
    expect(uploadErrorCode(new ApiError("x", 0))).toBe("network");
    expect(uploadErrorCode(new UploadError("storage_413"))).toBe("storage_413");
    expect(uploadErrorCode(new Error("?"))).toBe("upload_failed");
    expect(uploadErrorMessage(new UploadError("too_large"))).toMatch(/10 MB/);
    expect(uploadErrorMessage(new UploadError("network"))).toMatch(/didn't finish/);
  });
});

describe("pickImage", () => {
  it("returns null when the user cancels", async () => {
    pickReturns(null);
    expect(await pickImage()).toBeNull();
  });

  it("asks for images re-encoded below full quality (JPEG on iOS, not HEIC)", async () => {
    await pickImage();
    expect(picker.launchImageLibraryAsync).toHaveBeenCalledWith(expect.objectContaining({ mediaTypes: ["images"], quality: 0.8 }));
  });

  it("measures the file when the picker doesn't say its size", async () => {
    pickReturns({ uri: "file:///p.jpg", mimeType: "image/jpeg" });
    expect(await pickImage()).toEqual({ uri: "file:///p.jpg", mimeType: "image/jpeg", sizeBytes: 777 });
  });
});

describe("putFile", () => {
  const image = { uri: PHOTO.uri, mimeType: "image/jpeg", sizeBytes: 2048 };

  it("PUTs the file to the signed URL and reports progress to 100%", async () => {
    const progress: number[] = [];
    await putFile(TICKET.signedUrl, image, "image/jpeg", (p) => progress.push(p));
    expect(sent).toHaveLength(1);
    expect(sent[0]?.method).toBe("PUT");
    expect(sent[0]?.url).toBe(TICKET.signedUrl);
    expect(sent[0]?.body).toBeInstanceOf(FormData);
    expect(progress).toEqual([0.4, 1]);
  });

  it.each([
    [{ status: 413 }, "storage_413"],
    [{ fail: "network" as const }, "network"],
    [{ fail: "timeout" as const }, "timeout"],
  ])("fails with a code Storage or the network gave (%o)", async (outcome, code) => {
    outcomes.push(outcome);
    await expect(putFile(TICKET.signedUrl, image, "image/jpeg", () => undefined)).rejects.toThrow(code);
  });
});

// ---- the hook --------------------------------------------------------------------------------------

async function setup() {
  const onUploaded = jest.fn();
  const hook = await renderHook(() => useImageUpload({ onUploaded }));
  return { ...hook, onUploaded };
}

describe("useImageUpload", () => {
  it("picks, uploads and records success once", async () => {
    const { result, onUploaded } = await setup();
    await act(() => result.current.pick());
    expect(api.createUpload).toHaveBeenCalledWith("image/jpeg", 2048);
    expect(sent).toHaveLength(1);
    expect(api.completeUpload).toHaveBeenCalledWith("u-1");
    expect(result.current.state).toMatchObject({ status: "done", progress: 1, upload: UPLOAD });
    expect(onUploaded).toHaveBeenCalledWith(UPLOAD);
    expect(analytics.imageUploaded).toHaveBeenCalledTimes(1);
    expect(analytics.imageUploaded).toHaveBeenCalledWith({ success: true, error_code: null, duration_ms: 42, attempt: 1 });
  });

  it("a cancelled pick changes nothing and records nothing", async () => {
    pickReturns(null);
    const { result } = await setup();
    await act(() => result.current.pick());
    expect(result.current.state.status).toBe("idle");
    expect(analytics.imageUploaded).not.toHaveBeenCalled();
  });

  it("a failed PUT is shown, recorded, and retried with the same ticket", async () => {
    outcomes.push({ status: 500 });
    const { result, onUploaded } = await setup();
    await act(() => result.current.pick());
    expect(result.current.state).toMatchObject({ status: "error", canRetry: true });
    expect(result.current.state.error).toMatch(/didn't finish/);
    expect(analytics.imageUploaded).toHaveBeenLastCalledWith({ success: false, error_code: "storage_500", duration_ms: 42, attempt: 1 });

    await act(() => result.current.retry());
    expect(api.createUpload).toHaveBeenCalledTimes(1);
    expect(sent).toHaveLength(2);
    expect(result.current.state.status).toBe("done");
    expect(onUploaded).toHaveBeenCalledTimes(1);
    expect(analytics.imageUploaded).toHaveBeenLastCalledWith({ success: true, error_code: null, duration_ms: 42, attempt: 2 });
  });

  it("when only the confirmation failed, a retry never sends the file again", async () => {
    api.completeUpload.mockRejectedValueOnce(new ApiError("offline", 0));
    const { result } = await setup();
    await act(() => result.current.pick());
    expect(result.current.state.status).toBe("error");
    await act(() => result.current.retry());
    expect(sent).toHaveLength(1);
    expect(api.completeUpload).toHaveBeenCalledTimes(2);
    expect(result.current.state.status).toBe("done");
  });

  it("when the server rejects what landed, a retry starts over", async () => {
    api.completeUpload.mockRejectedValueOnce(new ApiError("rejected", 422));
    const { result } = await setup();
    await act(() => result.current.pick());
    expect(result.current.state.error).toMatch(/couldn't be accepted/);
    await act(() => result.current.retry());
    expect(api.createUpload).toHaveBeenCalledTimes(2);
    expect(sent).toHaveLength(2);
  });

  it("a photo that is too big fails before any request and can't be retried", async () => {
    pickReturns({ ...PHOTO, fileSize: MAX_UPLOAD_BYTES + 1 });
    const { result } = await setup();
    await act(() => result.current.pick());
    expect(result.current.state).toMatchObject({ status: "error", canRetry: false });
    expect(api.createUpload).not.toHaveBeenCalled();
    expect(analytics.imageUploaded).toHaveBeenCalledWith({ success: false, error_code: "too_large", duration_ms: 0, attempt: 1 });
    await act(() => result.current.retry());
    expect(api.createUpload).not.toHaveBeenCalled();
  });

  it("a picker that throws is reported, not swallowed", async () => {
    picker.launchImageLibraryAsync.mockRejectedValueOnce(new Error("no photos access"));
    const { result } = await setup();
    await act(() => result.current.pick());
    expect(result.current.state.status).toBe("error");
    expect(analytics.imageUploaded).toHaveBeenCalledWith(expect.objectContaining({ success: false, error_code: "picker_failed" }));
  });

  it("reset clears a finished upload", async () => {
    const { result } = await setup();
    await act(() => result.current.pick());
    await act(async () => result.current.reset());
    expect(result.current.state.status).toBe("idle");
  });
});
