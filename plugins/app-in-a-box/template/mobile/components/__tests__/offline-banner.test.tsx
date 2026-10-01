/**
 * OfflineBanner follows TanStack Query's onlineManager (fed by NetInfo), is
 * announced once, carries text (not colour alone) and never blocks taps.
 */
import { AccessibilityInfo } from "react-native";
import { onlineManager } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react-native";

import { en } from "../../locales/en";
import { OfflineBanner } from "../ui";

jest.mock("react-native-safe-area-context", () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));

afterEach(() => onlineManager.setOnline(true));

it("renders nothing while online", async () => {
  onlineManager.setOnline(true);
  await render(<OfflineBanner />);
  expect(screen.queryByTestId("offline-banner")).toBeNull();
});

it("appears when connectivity drops and goes away when it's back", async () => {
  const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);
  onlineManager.setOnline(true);
  await render(<OfflineBanner />);

  await act(async () => onlineManager.setOnline(false));
  const banner = await screen.findByTestId("offline-banner");
  expect(banner.props.accessibilityRole).toBe("alert");
  expect(banner.props.accessibilityLabel).toBe(en.offline.banner);
  expect(screen.getByText(en.offline.banner)).toBeTruthy();
  expect(announce).toHaveBeenCalledWith(en.offline.banner);

  await act(async () => onlineManager.setOnline(true));
  expect(screen.queryByTestId("offline-banner")).toBeNull();
  announce.mockRestore();
});

it("never intercepts touches (the app stays usable offline)", async () => {
  await render(<OfflineBanner online={false} />);
  expect(screen.getByTestId("offline-banner-host").props.pointerEvents).toBe("none");
});
