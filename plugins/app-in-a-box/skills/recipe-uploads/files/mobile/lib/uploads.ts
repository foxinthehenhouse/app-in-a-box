/**
 * Image uploads (added by the recipe-uploads skill): pick a photo, send it, show
 * progress, retry what failed.
 *
 *   const upload = useImageUpload({ onUploaded: (u) => save(u.id) });
 *   upload.pick();  upload.retry();  upload.state.progress  // 0..1
 *
 * The bytes go straight to Supabase Storage, never through our API:
 *   1. createUpload()   POST /api/v1/uploads: the server checks type + size and
 *                       signs a URL for a path IT chose (your folder, a new uuid)
 *   2. putFile()        PUT to that URL with XMLHttpRequest (fetch has no upload
 *                       progress in React Native); the bucket enforces the limits
 *   3. completeUpload() the server reads what actually landed and records it
 * A retry resumes at the step that failed: a finished PUT is never sent twice.
 *
 * Every attempt fires `imageUploaded` with success or an error_code, so a failed
 * upload leaves a trail (the analytics rule). Errors are shown, never swallowed.
 */
import { useCallback, useRef, useState } from "react";
import { File } from "expo-file-system";
import * as ImagePicker from "expo-image-picker";

import { analytics, startTimer } from "./analytics";
import {
  ApiError,
  completeUpload,
  createUpload,
  errorMessage,
  errorReference,
  type Upload,
  type UploadContentType,
  type UploadTicket,
} from "./api";
import { DEMO } from "./demo";
import { i18n } from "./i18n";

/** Mirrors backend/services/uploads_service.py. The server re-checks both. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const UPLOAD_TYPES: readonly UploadContentType[] = ["image/jpeg", "image/png", "image/webp", "image/heic"];
/** A stalled upload on a bad connection fails (and can be retried) instead of hanging. */
export const UPLOAD_TIMEOUT_MS = 120_000;

export interface PickedImage {
  uri: string;
  mimeType: string;
  sizeBytes: number;
}

export class UploadError extends Error {
  constructor(public readonly code: string) {
    super(code);
    this.name = "UploadError";
  }
}

const EXT_TYPES: Record<string, UploadContentType> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  heic: "image/heic",
};

/** The picker's mimeType, else the file extension. Pure for tests. */
export function contentTypeOf(image: Pick<PickedImage, "uri" | "mimeType">): string {
  if (image.mimeType) return image.mimeType.toLowerCase();
  const ext = image.uri.split("?")[0]?.split(".").pop()?.toLowerCase() ?? "";
  return EXT_TYPES[ext] ?? "";
}

/** Checked before a request is made, so the user hears "too big" without a round trip. */
export function checkImage(image: PickedImage): UploadContentType {
  const type = contentTypeOf(image);
  const allowed = UPLOAD_TYPES.find((t) => t === type);
  if (!allowed) throw new UploadError("unsupported_type");
  if (!(image.sizeBytes > 0)) throw new UploadError("empty_file");
  if (image.sizeBytes > MAX_UPLOAD_BYTES) throw new UploadError("too_large");
  return allowed;
}

/**
 * The system photo picker. On iOS 14+ and Android 13+ it needs no permission prompt
 * (the OS shows only what the user picks). `quality` < 1 makes iOS hand over a JPEG
 * instead of HEIC, which every browser can show. Null when the user cancels.
 */
export async function pickImage(): Promise<PickedImage | null> {
  const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.8, allowsMultipleSelection: false });
  const asset = result.canceled ? undefined : result.assets[0];
  if (!asset) return null;
  const sizeBytes = asset.fileSize ?? new File(asset.uri).size ?? 0;
  return { uri: asset.uri, mimeType: asset.mimeType ?? "", sizeBytes };
}

/**
 * PUT the file to a signed Storage URL, reporting progress 0..1. Multipart, the way
 * supabase-js sends it, so React Native streams the file from disk instead of
 * loading it into JS memory.
 */
export function putFile(url: string, image: PickedImage, type: UploadContentType, onProgress: (p: number) => void): Promise<void> {
  if (DEMO) {
    onProgress(1);
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.timeout = UPLOAD_TIMEOUT_MS;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && e.total > 0) onProgress(Math.min(1, e.loaded / e.total));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(1);
        resolve();
      } else reject(new UploadError(`storage_${xhr.status}`));
    };
    xhr.onerror = () => reject(new UploadError("network"));
    xhr.ontimeout = () => reject(new UploadError("timeout"));
    const form = new FormData();
    form.append("cacheControl", "3600");
    // React Native's FormData takes a { uri, name, type } file part.
    form.append("", { uri: image.uri, name: "upload", type } as unknown as Blob);
    xhr.send(form);
  });
}

/** For analytics: a stable, PII-free code for what went wrong. */
export function uploadErrorCode(e: unknown): string {
  if (e instanceof UploadError) return e.code;
  if (e instanceof ApiError) return e.status === 0 ? "network" : `http_${e.status}`;
  return "upload_failed";
}

const MB = MAX_UPLOAD_BYTES / (1024 * 1024);
const MESSAGES: Record<string, () => string> = {
  unsupported_type: () => i18n.t("uploads.unsupportedType"),
  empty_file: () => i18n.t("uploads.emptyFile"),
  too_large: () => i18n.t("uploads.tooLarge", { mb: MB }),
  http_422: () => i18n.t("uploads.rejected", { mb: MB }),
  http_429: () => i18n.t("uploads.slowDown"),
};

/** A short, human message for the screen. */
export function uploadErrorMessage(e: unknown): string {
  const message = MESSAGES[uploadErrorCode(e)];
  if (message) return message();
  if (e instanceof UploadError) return i18n.t("uploads.failed");
  return errorMessage(e);
}

export type UploadStatus = "idle" | "uploading" | "done" | "error";

export interface UploadState {
  status: UploadStatus;
  /** 0..1 while uploading. */
  progress: number;
  /** The picked photo (shown as the preview while it uploads). */
  image: PickedImage | null;
  upload: Upload | null;
  error: string | null;
  errorRef: string | null;
  /** The failed upload can be retried (a photo that's too big can't: pick another). */
  canRetry: boolean;
}

const IDLE: UploadState = { status: "idle", progress: 0, image: null, upload: null, error: null, errorRef: null, canRetry: false };

/** Where a retry picks up: no ticket yet, the PUT, or just the server's confirmation. */
interface Pending {
  image: PickedImage;
  type: UploadContentType;
  ticket: UploadTicket | null;
  sent: boolean;
  attempt: number;
}

export function useImageUpload(opts: { onUploaded?: (u: Upload) => void } = {}) {
  const [state, setState] = useState<UploadState>(IDLE);
  const pending = useRef<Pending | null>(null);
  const busy = useRef(false);
  const { onUploaded } = opts;

  const run = useCallback(
    async (job: Pending) => {
      if (busy.current) return;
      busy.current = true;
      const elapsed = startTimer();
      setState({ ...IDLE, status: "uploading", image: job.image, progress: job.sent ? 1 : 0 });
      try {
        const ticket = job.ticket ?? (await createUpload(job.type, job.image.sizeBytes));
        job.ticket = ticket;
        if (!job.sent) {
          await putFile(ticket.signedUrl, job.image, job.type, (progress) => setState((s) => ({ ...s, progress })));
          job.sent = true;
        }
        const upload = await completeUpload(ticket.uploadId);
        pending.current = null;
        analytics.imageUploaded({ success: true, error_code: null, duration_ms: elapsed(), attempt: job.attempt });
        setState({ ...IDLE, status: "done", progress: 1, image: job.image, upload });
        onUploaded?.(upload);
      } catch (e) {
        analytics.imageUploaded({ success: false, error_code: uploadErrorCode(e), duration_ms: elapsed(), attempt: job.attempt });
        // A 4xx on the confirmation means this object will never be accepted: start over.
        if (e instanceof ApiError && e.status >= 400 && e.status < 500 && job.sent) {
          job.ticket = null;
          job.sent = false;
        }
        setState((s) => ({ ...s, status: "error", error: uploadErrorMessage(e), errorRef: errorReference(e), canRetry: true }));
      } finally {
        busy.current = false;
      }
    },
    [onUploaded],
  );

  /** Open the picker; a picked photo starts uploading at once. Cancel changes nothing. */
  const pick = useCallback(async () => {
    if (busy.current) return;
    let image: PickedImage | null;
    try {
      image = await pickImage();
    } catch (e) {
      analytics.imageUploaded({ success: false, error_code: "picker_failed", duration_ms: 0, attempt: 0 });
      setState({ ...IDLE, status: "error", error: uploadErrorMessage(e) });
      return;
    }
    if (!image) return;
    let type: UploadContentType;
    try {
      type = checkImage(image);
    } catch (e) {
      pending.current = null;
      analytics.imageUploaded({ success: false, error_code: uploadErrorCode(e), duration_ms: 0, attempt: 1 });
      setState({ ...IDLE, status: "error", image, error: uploadErrorMessage(e) });
      return;
    }
    const job: Pending = { image, type, ticket: null, sent: false, attempt: 1 };
    pending.current = job;
    await run(job);
  }, [run]);

  /** Try the failed upload again, from the step that failed. No-op if nothing failed. */
  const retry = useCallback(async () => {
    const job = pending.current;
    if (!job) return;
    job.attempt += 1;
    await run(job);
  }, [run]);

  const reset = useCallback(() => {
    if (busy.current) return;
    pending.current = null;
    setState(IDLE);
  }, []);

  return { state, pick, retry, reset };
}
