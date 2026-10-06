/**
 * ImageUpload (recipe-uploads): what a person sees and hears while a photo uploads,
 * and that "Try again" finishes the job after a failure.
 */
import { AccessibilityInfo } from "react-native";
import { act, fireEvent, render, screen } from "@testing-library/react-native";

import type { Upload } from "../../lib/api";
import { ImageUpload } from "../ui/ImageUpload";

jest.mock("expo-clipboard", () => ({ setStringAsync: jest.fn(() => Promise.resolve(true)) }));
jest.mock("../../lib/supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn() }));
jest.mock("../../lib/analytics", () => ({
  analytics: { apiFailed: jest.fn(), imageUploaded: jest.fn(), errorReferenceCopied: jest.fn() },
  startTimer: () => () => 1,
}));
jest.mock("expo-image-picker", () => ({
  launchImageLibraryAsync: jest.fn(async () => ({
    canceled: false,
    assets: [{ uri: "file:///photo.jpg", mimeType: "image/jpeg", fileSize: 1000 }],
  })),
}));
// Demo mode skips the Storage PUT (lib/uploads.ts putFile), so no network is involved.
jest.mock("../../lib/demo", () => ({ ...jest.requireActual("../../lib/demo"), DEMO: true }));
jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    ...actual,
    createUpload: jest.fn(async () => ({ uploadId: "u-1", signedUrl: "https://storage/u-1" })),
    completeUpload: jest.fn(),
  };
});

const api = jest.requireMock("../../lib/api") as { completeUpload: jest.Mock };
const UPLOAD: Upload = { id: "u-1", contentType: "image/jpeg", sizeBytes: 1000, createdAt: "2026-10-04T10:00:00Z", url: "https://cdn/u-1" };
const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);

beforeEach(() => {
  jest.clearAllMocks();
  api.completeUpload.mockResolvedValue(UPLOAD);
});

it("starts with one purpose-labelled button and no preview", async () => {
  await render(<ImageUpload testID="photo" />);
  const button = screen.getByTestId("photo-choose-button");
  expect(button.props.accessibilityLabel).toBe("Choose a photo to upload");
  expect(screen.queryByTestId("photo-preview")).toBeNull();
});

it("shows the photo, announces success and hands the upload back", async () => {
  const onUploaded = jest.fn();
  await render(<ImageUpload onUploaded={onUploaded} testID="photo" />);
  await act(async () => {
    await fireEvent.press(screen.getByTestId("photo-choose-button"));
  });
  expect(screen.getByTestId("photo-preview")).toBeTruthy();
  expect(screen.getByTestId("photo-done")).toBeTruthy();
  expect(announce).toHaveBeenCalledWith("Photo uploaded");
  expect(onUploaded).toHaveBeenCalledWith(UPLOAD);
  expect(screen.getByText("Choose another photo")).toBeTruthy();
});

it("says what failed and finishes on Try again", async () => {
  api.completeUpload.mockRejectedValueOnce(new Error("offline"));
  const onUploaded = jest.fn();
  await render(<ImageUpload onUploaded={onUploaded} testID="photo" />);
  await act(async () => {
    await fireEvent.press(screen.getByTestId("photo-choose-button"));
  });
  expect(screen.getByTestId("photo-error-message").props.accessibilityRole).toBe("alert");
  expect(onUploaded).not.toHaveBeenCalled();
  await act(async () => {
    await fireEvent.press(screen.getByTestId("photo-error-retry-button"));
  });
  expect(screen.getByTestId("photo-done")).toBeTruthy();
  expect(onUploaded).toHaveBeenCalledWith(UPLOAD);
});
