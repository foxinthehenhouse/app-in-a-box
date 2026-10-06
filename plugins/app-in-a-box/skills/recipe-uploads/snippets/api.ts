
// ---- Image uploads (recipe-uploads) -----------------------------------------

/** Mirrors backend/routers/uploads.py `ContentType`: the API refuses anything else (422). */
export type UploadContentType = "image/jpeg" | "image/png" | "image/webp" | "image/heic";

/** Mirrors backend/routers/uploads.py `UploadRequest` (POST /api/v1/uploads). */
export interface UploadRequestWire {
  contentType: "image/jpeg" | "image/png" | "image/webp" | "image/heic";
  sizeBytes: number;
}

/** Mirrors backend/routers/uploads.py `UploadTicket`: a signed URL for one object. */
export interface UploadTicketWire {
  uploadId: string;
  signedUrl: string;
}

/** Mirrors backend/routers/uploads.py `Upload`. `downloadUrl` is signed and expires (1 h). */
export interface UploadWire {
  id: string;
  contentType: string;
  sizeBytes: number;
  createdAt: string;
  downloadUrl: string;
}

/** Mirrors backend/routers/uploads.py `UploadList`. */
export interface UploadListWire {
  items: UploadWire[];
}

export type UploadTicket = UploadTicketWire;

export interface Upload {
  id: string;
  contentType: string;
  sizeBytes: number;
  createdAt: string;
  /** Empty when the server couldn't sign one; show the placeholder, refetch later. */
  url: string;
}

export function toUpload(w: UploadWire): Upload {
  return { id: w.id, contentType: w.contentType, sizeBytes: w.sizeBytes, createdAt: w.createdAt, url: w.downloadUrl };
}

export async function createUpload(contentType: UploadContentType, sizeBytes: number): Promise<UploadTicket> {
  const body: UploadRequestWire = { contentType, sizeBytes };
  return apiFetch<UploadTicketWire>("/api/v1/uploads", { method: "POST", body: JSON.stringify(body) });
}

export async function completeUpload(uploadId: string): Promise<Upload> {
  return toUpload(await apiFetch<UploadWire>(`/api/v1/uploads/${encodeURIComponent(uploadId)}/complete`, { method: "POST" }));
}

export async function listUploads(): Promise<Upload[]> {
  const w = await apiFetch<UploadListWire>("/api/v1/uploads");
  return (w.items ?? []).map(toUpload);
}

export async function deleteUpload(uploadId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/uploads/${encodeURIComponent(uploadId)}`, { method: "DELETE" });
}
