/**
 * Toast queue: a pure reducer, so ordering, de-duplication and the visible cap
 * are unit-tested without rendering anything. components/ui/Toast.tsx renders it.
 */
export type ToastKind = "success" | "error" | "info";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  /** ms before auto-dismiss. Errors stay longer: people need time to read them. */
  duration: number;
}

export interface ToastState {
  items: ToastItem[];
  nextId: number;
}

export const MAX_VISIBLE = 3;
export const DEFAULT_DURATION: Record<ToastKind, number> = { success: 2600, info: 3200, error: 5000 };

export const initialToastState: ToastState = { items: [], nextId: 1 };

export type ToastAction =
  | { type: "show"; kind: ToastKind; message: string; duration?: number }
  | { type: "dismiss"; id: number }
  | { type: "clear" };

export function toastReducer(state: ToastState, action: ToastAction): ToastState {
  switch (action.type) {
    case "show": {
      // The same message twice in a row (a double tap) shows once.
      const last = state.items[state.items.length - 1];
      if (last && last.message === action.message && last.kind === action.kind) return state;
      const item: ToastItem = {
        id: state.nextId,
        kind: action.kind,
        message: action.message,
        duration: action.duration ?? DEFAULT_DURATION[action.kind],
      };
      // Newest last; drop the oldest beyond the cap so the stack never grows unbounded.
      return { items: [...state.items, item].slice(-MAX_VISIBLE), nextId: state.nextId + 1 };
    }
    case "dismiss":
      return { ...state, items: state.items.filter((t) => t.id !== action.id) };
    case "clear":
      return { ...state, items: [] };
  }
}
