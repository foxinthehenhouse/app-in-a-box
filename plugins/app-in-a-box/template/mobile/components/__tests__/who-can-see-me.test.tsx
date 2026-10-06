/**
 * WhoCanSeeMe (the location pack): names who can see the user's location as one
 * labelled element, in text (never colour alone), with a 48px way to change it.
 */
import { fireEvent, render, screen } from "@testing-library/react-native";

import { en } from "../../locales/en";
import { WhoCanSeeMe } from "../ui/WhoCanSeeMe";

it("says who can see the location, as text and as one spoken label", async () => {
  await render(<WhoCanSeeMe audience="Sam and Alex" />);
  expect(screen.getByText(en.location.visibleTo)).toBeTruthy();
  expect(screen.getByTestId("who-can-see-me-audience").props.children).toBe("Sam and Alex");
  expect(screen.getByLabelText("Who can see your location: Sam and Alex")).toBeTruthy();
  expect(screen.queryByTestId("who-can-see-me-manage-button")).toBeNull();
});

it("offers a way to change it when sharing can change", async () => {
  const onManage = jest.fn();
  await render(<WhoCanSeeMe audience="Only you" onManage={onManage} />);
  const button = screen.getByTestId("who-can-see-me-manage-button");
  expect(button.props.accessibilityLabel).toBe(en.location.manageLabel);
  await fireEvent.press(button);
  expect(onManage).toHaveBeenCalledTimes(1);
});
