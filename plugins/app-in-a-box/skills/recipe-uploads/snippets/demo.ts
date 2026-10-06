  // Mirrors backend/routers/uploads.py without Storage: lib/uploads.ts skips the PUT in
  // demo mode, the photo stays on the device, and nothing is listed.
  "POST /api/v1/uploads": () => ({
    status: 200,
    body: { uploadId: `demo-${Date.now().toString(36)}`, signedUrl: "demo://upload" },
  }),
  "POST /api/v1/uploads/:id/complete": (_body, { params }) => ({
    status: 200,
    body: { id: params.id, contentType: "image/jpeg", sizeBytes: 1, createdAt: new Date().toISOString(), downloadUrl: "" },
  }),
  "GET /api/v1/uploads": () => ({ status: 200, body: { items: [] } }),
  "DELETE /api/v1/uploads/:id": () => ({ status: 204, body: undefined }),
