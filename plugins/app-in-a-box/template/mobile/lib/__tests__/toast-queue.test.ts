import { DEFAULT_DURATION, MAX_VISIBLE, initialToastState, toastReducer, type ToastState } from "../toast-queue";

const show = (s: ToastState, message: string, kind: "success" | "error" | "info" = "info") =>
  toastReducer(s, { type: "show", kind, message });

describe("toastReducer", () => {
  it("queues newest last with unique ids and per-kind durations", () => {
    let s = show(initialToastState, "Saved", "success");
    s = show(s, "Couldn't save", "error");
    expect(s.items.map((t) => t.message)).toEqual(["Saved", "Couldn't save"]);
    expect(new Set(s.items.map((t) => t.id)).size).toBe(2);
    expect(s.items[1]?.duration).toBe(DEFAULT_DURATION.error);
    expect(DEFAULT_DURATION.error).toBeGreaterThan(DEFAULT_DURATION.success);
  });

  it("collapses an identical back-to-back toast (a double tap)", () => {
    const s = show(show(initialToastState, "Saved", "success"), "Saved", "success");
    expect(s.items).toHaveLength(1);
  });

  it("caps the visible stack, dropping the oldest", () => {
    let s = initialToastState;
    for (let i = 0; i < MAX_VISIBLE + 2; i++) s = show(s, `m${i}`);
    expect(s.items).toHaveLength(MAX_VISIBLE);
    expect(s.items[0]?.message).toBe("m2");
  });

  it("dismisses by id and clears", () => {
    const s = show(show(initialToastState, "a"), "b");
    const first = s.items[0];
    if (!first) throw new Error("expected a toast");
    expect(toastReducer(s, { type: "dismiss", id: first.id }).items.map((t) => t.message)).toEqual(["b"]);
    expect(toastReducer(s, { type: "clear" }).items).toEqual([]);
  });
});
