  /** An image upload attempt finished (recipe-uploads). `attempt` counts retries of the same photo. */
  imageUploaded: (p: { success: boolean; error_code: string | null; duration_ms: number; attempt: number }) =>
    capture("image_uploaded", p),
