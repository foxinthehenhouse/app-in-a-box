import { ApiError, errorMessage, toProfile } from "../api";

jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn() }));
jest.mock("../analytics", () => ({ analytics: { apiFailed: jest.fn() }, startTimer: () => () => 0 }));

describe("toProfile", () => {
  it("maps a null display name to an empty string, not 'null'", () => {
    expect(toProfile({ id: "u1", displayName: null, onboarded: false })).toEqual({
      id: "u1",
      displayName: "",
      onboarded: false,
    });
  });
});

describe("errorMessage", () => {
  it("says offline for a network failure, and never leaks a stack", () => {
    expect(errorMessage(new ApiError("fetch failed", 0))).toMatch(/offline/);
    expect(errorMessage(new ApiError("x", 500))).toBe("Something went wrong (500). Try again.");
    expect(errorMessage(new Error("TypeError at line 3"))).toBe("Something went wrong. Try again.");
  });
});
