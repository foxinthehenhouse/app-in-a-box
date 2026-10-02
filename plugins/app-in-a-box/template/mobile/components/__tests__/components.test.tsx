/**
 * Behaviour tests for the UI kit: what a screen reader hears, what the hand feels
 * (haptics), and what renders or stays out of the way. Each test asserts an outcome
 * a user would notice if it broke, not just that a testID exists.
 */
import { AccessibilityInfo, Pressable, Text as RNText } from "react-native";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import * as Haptics from "expo-haptics";

import { Button } from "../ui/Button";
import { Celebration } from "../ui/Celebration";
import { Chip } from "../ui/Choice";
import { ErrorNotice } from "../ui/ErrorNotice";
import { EmptyState } from "../ui/Feedback";
import { Media, aspect } from "../ui/Media";
import { SkeletonCard } from "../ui/Skeleton";
import { StatCard } from "../ui/Stat";
import { ToastProvider, useToast } from "../ui/Toast";
import { Toggle } from "../ui/Toggle";
import { ListRow } from "../ui/ListRow";
import { UpdateBanner } from "../ui/UpdateBanner";

// Toast and UpdateBanner sit above the safe area; a notched-phone inset proves they use it.
jest.mock("react-native-safe-area-context", () => ({ useSafeAreaInsets: () => ({ top: 47, bottom: 34, left: 0, right: 0 }) }));

jest.mock("expo-clipboard", () => ({ setStringAsync: jest.fn(() => Promise.resolve(true)) }));

jest.mock("expo-haptics", () => ({
  selectionAsync: jest.fn(() => Promise.resolve()),
  impactAsync: jest.fn(() => Promise.resolve()),
  notificationAsync: jest.fn(() => Promise.resolve()),
  ImpactFeedbackStyle: { Light: "light", Medium: "medium", Heavy: "heavy" },
  NotificationFeedbackType: { Success: "success", Warning: "warning", Error: "error" },
}));

const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);

beforeEach(() => {
  jest.clearAllMocks();
});

describe("haptics are graded by commitment", () => {
  it("a primary button fires a medium impact on press-in", async () => {
    await render(<Button label="Save" onPress={() => undefined} testID="b" />);
    await fireEvent(screen.getByTestId("b"), "pressIn");
    expect(Haptics.impactAsync).toHaveBeenCalledWith(Haptics.ImpactFeedbackStyle.Medium);
  });

  it("a secondary button fires a light impact", async () => {
    await render(<Button label="Cancel" variant="secondary" onPress={() => undefined} testID="b" />);
    await fireEvent(screen.getByTestId("b"), "pressIn");
    expect(Haptics.impactAsync).toHaveBeenCalledWith(Haptics.ImpactFeedbackStyle.Light);
    expect(Haptics.impactAsync).not.toHaveBeenCalledWith(Haptics.ImpactFeedbackStyle.Medium);
  });

  it("a disabled button gives no haptic and doesn't fire", async () => {
    const onPress = jest.fn();
    await render(<Button label="Save" disabled onPress={onPress} testID="b" />);
    await fireEvent(screen.getByTestId("b"), "pressIn");
    await fireEvent.press(screen.getByTestId("b"));
    expect(Haptics.impactAsync).not.toHaveBeenCalled();
    expect(onPress).not.toHaveBeenCalled();
  });

  it("a haptic that throws on unsupported hardware never crashes the press", async () => {
    (Haptics.impactAsync as jest.Mock).mockImplementationOnce(() => {
      throw new Error("not supported");
    });
    const onPress = jest.fn();
    await render(<Button label="Save" onPress={onPress} testID="b" />);
    await expect((async () => { await fireEvent(screen.getByTestId("b"), "pressIn"); })()).resolves.toBeUndefined();
    await fireEvent.press(screen.getByTestId("b"));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});

function ToastTrigger({ kind, message }: { kind: "success" | "error" | "info"; message: string }) {
  const toast = useToast();
  return (
    <Pressable testID="trigger" onPress={() => toast[kind](message)}>
      <RNText>go</RNText>
    </Pressable>
  );
}

describe("Toast", () => {
  it("an error is announced, felt as an error, and shown as an alert", async () => {
    await render(
      <ToastProvider>
        <ToastTrigger kind="error" message="Couldn't save. Try again." />
      </ToastProvider>,
    );
    await fireEvent.press(screen.getByTestId("trigger"));
    const toast = await screen.findByTestId("toast-error");
    expect(toast.props.accessibilityRole).toBe("alert");
    expect(toast.props.accessibilityLabel).toBe("Couldn't save. Try again.");
    expect(announce).toHaveBeenCalledWith("Couldn't save. Try again.");
    expect(Haptics.notificationAsync).toHaveBeenCalledWith(Haptics.NotificationFeedbackType.Error);
  });

  it("a success is felt as success; an info toast stays silent to the hand", async () => {
    await render(
      <ToastProvider>
        <ToastTrigger kind="success" message="Saved" />
      </ToastProvider>,
    );
    await fireEvent.press(screen.getByTestId("trigger"));
    expect(Haptics.notificationAsync).toHaveBeenCalledWith(Haptics.NotificationFeedbackType.Success);

    jest.clearAllMocks();
    await render(
      <ToastProvider>
        <ToastTrigger kind="info" message="Synced" />
      </ToastProvider>,
    );
    await fireEvent.press(screen.getByTestId("trigger"));
    expect(await screen.findByTestId("toast-info")).toBeTruthy();
    expect(Haptics.notificationAsync).not.toHaveBeenCalled();
  });

  it("tapping a toast dismisses it, without a second haptic", async () => {
    await render(
      <ToastProvider>
        <ToastTrigger kind="success" message="Saved" />
      </ToastProvider>,
    );
    await fireEvent.press(screen.getByTestId("trigger"));
    const toast = await screen.findByTestId("toast-success");
    jest.clearAllMocks();
    await fireEvent(toast, "pressIn");
    await fireEvent.press(toast);
    expect(screen.queryByTestId("toast-success")).toBeNull();
    expect(Haptics.impactAsync).not.toHaveBeenCalled();
  });

  it("a toast dismisses itself after its duration", async () => {
    jest.useFakeTimers();
    try {
      await render(
        <ToastProvider>
          <ToastTrigger kind="info" message="Synced" />
        </ToastProvider>,
      );
      await fireEvent.press(screen.getByTestId("trigger"));
      expect(screen.getByTestId("toast-info")).toBeTruthy();
      await act(async () => {
        jest.advanceTimersByTime(10_000);
      });
      expect(screen.queryByTestId("toast-info")).toBeNull();
    } finally {
      jest.useRealTimers();
    }
  });
});

describe("SkeletonCard", () => {
  it("is one busy 'loading' element for screen readers, and announces a screen load", async () => {
    await render(<SkeletonCard announce="Loading your profile" testID="sk" />);
    const card = screen.getByTestId("sk");
    expect(card.props.accessible).toBe(true);
    expect(card.props.accessibilityLabel).toBe("Loading your profile");
    expect(card.props.accessibilityState).toEqual({ busy: true });
    expect(announce).toHaveBeenCalledWith("Loading your profile");
  });

  it("falls back to a generic label and stays quiet without `announce`", async () => {
    await render(<SkeletonCard testID="sk" />);
    expect(screen.getByTestId("sk").props.accessibilityLabel).toBeTruthy();
    expect(announce).not.toHaveBeenCalled();
  });
});

describe("EmptyState", () => {
  it("says what's missing, why, and offers the one next step", async () => {
    await render(
      <EmptyState
        icon={{ sf: "tray", md: "inbox" }}
        title="No entries yet"
        body="Your first entry starts the streak."
        action={<Button label="Add entry" onPress={() => undefined} testID="add" />}
        testID="empty"
      />,
    );
    expect(screen.getByText("No entries yet")).toBeTruthy();
    expect(screen.getByText("Your first entry starts the streak.")).toBeTruthy();
    expect(screen.getByTestId("add")).toBeTruthy();
  });
});

describe("Celebration", () => {
  it("renders nothing until triggered", async () => {
    await render(<Celebration trigger={0} message="7-day streak!" testID="c" />);
    expect(screen.queryByTestId("c")).toBeNull();
    expect(announce).not.toHaveBeenCalled();
    expect(Haptics.notificationAsync).not.toHaveBeenCalled();
  });

  it("when triggered, announces the win and fires a success haptic", async () => {
    await render(<Celebration trigger={1} message="7-day streak!" testID="c" />);
    expect(screen.getByTestId("c")).toBeTruthy();
    expect(announce).toHaveBeenCalledWith("7-day streak!");
    expect(Haptics.notificationAsync).toHaveBeenCalledWith(Haptics.NotificationFeedbackType.Success);
  });
});

describe("Toggle", () => {
  it("is labelled by what it turns on and reports the new value", async () => {
    const onChange = jest.fn();
    await render(<Toggle value={false} onValueChange={onChange} accessibilityLabel="Push notifications" testID="t" />);
    const sw = screen.getByTestId("t");
    expect(sw.props.accessibilityLabel).toBe("Push notifications");
    await fireEvent(sw, "valueChange", true);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("passes disabled through to the native switch", async () => {
    await render(<Toggle value onValueChange={() => undefined} accessibilityLabel="Analytics" disabled testID="t" />);
    expect(screen.getByTestId("t").props.disabled).toBe(true);
  });
});

describe("Media", () => {
  it("without a source, is a labelled image placeholder (never an empty box)", async () => {
    await render(<Media label="Your progress photo" testID="m" />);
    const m = screen.getByTestId("m");
    expect(m.props.accessibilityRole).toBe("image");
    expect(m.props.accessibilityLabel).toBe("Your progress photo");
  });

  it("parses ratios and falls back to 4:3 on anything malformed", () => {
    expect(aspect("3:4")).toBe(0.75);
    expect(aspect("16:9")).toBeCloseTo(16 / 9);
    expect(aspect(undefined)).toBeCloseTo(4 / 3);
    expect(aspect("0:5")).toBeCloseTo(4 / 3);
    expect(aspect("wide")).toBeCloseTo(4 / 3);
  });
});

describe("StatCard", () => {
  it("is read as one sentence: label, value, hint", async () => {
    await render(<StatCard label="Streak" value="12 days" hint="Best yet" testID="s" />);
    expect(screen.getByLabelText("Streak, 12 days, Best yet")).toBeTruthy();
  });
});

describe("ErrorNotice", () => {
  it("says what failed and retries on tap", async () => {
    const onRetry = jest.fn();
    await render(<ErrorNotice message="Couldn't load your profile." onRetry={onRetry} testID="err" />);
    expect(screen.getByTestId("err-message").props.accessibilityRole).toBe("alert");
    expect(screen.getByText(/Couldn't load your profile\./)).toBeTruthy();
    await fireEvent.press(screen.getByTestId("err-retry-button"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("copies the support reference and confirms it", async () => {
    const Clipboard = jest.requireMock("expo-clipboard") as { setStringAsync: jest.Mock };
    await render(
      <ToastProvider>
        <ErrorNotice message="Something went wrong." reference="req_7f3a" testID="err" />
      </ToastProvider>,
    );
    await fireEvent.press(screen.getByTestId("err-reference"));
    expect(Clipboard.setStringAsync).toHaveBeenCalledWith("req_7f3a");
    expect(await screen.findByTestId("toast-info")).toBeTruthy();
  });
});

describe("Chip", () => {
  it("announces its checked state and gives a selection haptic, not an impact", async () => {
    const onPress = jest.fn();
    await render(<Chip label="Morning" selected onPress={onPress} testID="chip" />);
    const chip = screen.getByTestId("chip");
    expect(chip.props.accessibilityRole).toBe("togglebutton");
    expect(chip.props.accessibilityState).toEqual({ checked: true });
    await fireEvent(chip, "pressIn");
    await fireEvent.press(chip);
    expect(Haptics.selectionAsync).toHaveBeenCalled();
    expect(Haptics.impactAsync).not.toHaveBeenCalled();
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});

describe("ListRow", () => {
  it("a tappable row is one button named by its title and value", async () => {
    const onPress = jest.fn();
    await render(<ListRow title="Name" value="Sam" onPress={onPress} testID="row" />);
    const row = screen.getByTestId("row");
    expect(row.props.accessibilityRole).toBe("button");
    expect(row.props.accessibilityLabel).toBe("Name, Sam");
    await fireEvent.press(row);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("a row with a trailing control leaves the control reachable on its own", async () => {
    await render(
      <ListRow
        title="Analytics"
        trailing={<Toggle value onValueChange={() => undefined} accessibilityLabel="Analytics" testID="sw" />}
        testID="row"
      />,
    );
    expect(screen.getByTestId("row").props.accessible).toBe(false);
    expect(screen.getByTestId("sw")).toBeTruthy();
  });
});

describe("UpdateBanner", () => {
  it("is hidden until an update is ready", async () => {
    await render(<UpdateBanner visible={false} onRestart={() => undefined} onLater={() => undefined} />);
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("is an alert with restart and later, each doing its one job", async () => {
    const onRestart = jest.fn();
    const onLater = jest.fn();
    await render(<UpdateBanner visible onRestart={onRestart} onLater={onLater} />);
    expect(screen.getByTestId("update-banner").props.accessibilityRole).toBe("alert");
    await fireEvent.press(screen.getByTestId("update-restart-button"));
    await fireEvent.press(screen.getByTestId("update-later-button"));
    expect(onRestart).toHaveBeenCalledTimes(1);
    expect(onLater).toHaveBeenCalledTimes(1);
  });
});
