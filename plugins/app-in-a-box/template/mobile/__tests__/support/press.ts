/**
 * Route-test helpers (not a test file: jest ignores `__tests__/support/`, see the kit's
 * mobile-deps.sh `jest.testPathIgnorePatterns`).
 *
 * Form buttons are `disabled` until react-hook-form reports the form valid, and that
 * report lands a tick AFTER `fireEvent.changeText` resolves (zod resolvers validate
 * asynchronously). A press fired straight after typing lands on a disabled button and
 * does nothing, so the test stalls on the next screen. Wait for the control to enable,
 * as a person would, then press.
 */
import { fireEvent, screen, waitFor } from "expo-router/testing-library";

export async function pressWhenEnabled(testID: string): Promise<void> {
  await waitFor(() => {
    const state = screen.getByTestId(testID).props.accessibilityState as { disabled?: boolean } | undefined;
    if (state?.disabled) throw new Error(`${testID} is still disabled`);
  });
  await fireEvent.press(screen.getByTestId(testID));
}
