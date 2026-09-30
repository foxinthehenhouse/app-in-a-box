/**
 * Toasts: brief, non-blocking confirmation ("Saved") or failure ("Couldn't
 * save"). Mount <ToastProvider> once at the root; call `useToast()` anywhere.
 *
 *   const toast = useToast();
 *   toast.success("Saved");   toast.error("Couldn't save. Try again.");
 *
 * - Queue logic is the pure reducer in lib/toast-queue.ts (unit-tested).
 * - Every toast is announced to screen readers and fires a matching haptic.
 * - Errors stay 5s; tap a toast to dismiss it early.
 * - A root toast renders UNDER a native formSheet on iOS. From a sheet, dismiss
 *   the sheet first, then show the toast on the screen underneath.
 * - Reduce motion: fades only, no slide.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, type ReactNode } from "react";
import { AccessibilityInfo, StyleSheet, View } from "react-native";
import Animated, { FadeInUp, FadeOutUp, LinearTransition, ReduceMotion } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useT } from "../../lib/i18n";
import { curve, fadeIn, fadeOut, haptic, useReducedMotion } from "../../lib/motion";
import { makeStyles, motion } from "../../lib/theme";
import { initialToastState, toastReducer, type ToastItem, type ToastKind } from "../../lib/toast-queue";
import { Icon } from "./Icon";
import { PressableScale } from "./PressableScale";
import { Text } from "./Text";

export interface ToastApi {
  show: (message: string, kind?: ToastKind) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const noop = () => undefined;
const ToastContext = createContext<ToastApi>({ show: noop, success: noop, error: noop, info: noop });

export function useToast(): ToastApi {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(toastReducer, initialToastState);
  const show = useCallback((message: string, kind: ToastKind = "info") => {
    dispatch({ type: "show", kind, message });
    AccessibilityInfo.announceForAccessibility(message);
    if (kind === "success") haptic.success();
    else if (kind === "error") haptic.error();
  }, []);
  const api = useMemo<ToastApi>(
    () => ({
      show,
      success: (m) => show(m, "success"),
      error: (m) => show(m, "error"),
      info: (m) => show(m, "info"),
    }),
    [show],
  );
  const dismiss = useCallback((id: number) => dispatch({ type: "dismiss", id }), []);
  const insets = useSafeAreaInsets();
  const s = useStyles();
  return (
    <ToastContext.Provider value={api}>
      {children}
      <View pointerEvents="box-none" style={[s.host, { top: insets.top + 8 }]}>
        {state.items.map((item) => (
          <ToastView key={item.id} item={item} onDismiss={dismiss} />
        ))}
      </View>
    </ToastContext.Provider>
  );
}

const ICON: Record<ToastKind, { sf: "checkmark.circle.fill" | "exclamationmark.triangle.fill" | "info.circle.fill"; md: "check_circle" | "warning" | "info"; color: "success" | "danger" | "accent" }> = {
  success: { sf: "checkmark.circle.fill", md: "check_circle", color: "success" },
  error: { sf: "exclamationmark.triangle.fill", md: "warning", color: "danger" },
  info: { sf: "info.circle.fill", md: "info", color: "accent" },
};

function ToastView({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  const s = useStyles();
  const t = useT();
  const reduced = useReducedMotion();
  useEffect(() => {
    const t = setTimeout(() => onDismiss(item.id), item.duration);
    return () => clearTimeout(t);
  }, [item.id, item.duration, onDismiss]);
  const icon = ICON[item.kind];
  const enter = reduced
    ? fadeIn
    : FadeInUp.duration(motion.duration.screen).easing(curve("enter")).reduceMotion(ReduceMotion.System);
  const exit = reduced ? fadeOut : FadeOutUp.duration(motion.duration.fast).reduceMotion(ReduceMotion.System);
  return (
    <Animated.View entering={enter} exiting={exit} layout={reduced ? undefined : LinearTransition}>
      <PressableScale
        onPress={() => onDismiss(item.id)}
        haptic={null}
        accessibilityRole="alert"
        accessibilityLabel={item.message}
        accessibilityHint={t("common.dismissHint")}
        testID={`toast-${item.kind}`}
        style={s.toast}
      >
        <Icon sf={icon.sf} md={icon.md} size={20} color={icon.color} />
        <Text variant="body" style={s.message} numberOfLines={3}>
          {item.message}
        </Text>
      </PressableScale>
    </Animated.View>
  );
}

const useStyles = makeStyles((t) => ({
  host: { position: "absolute", left: t.space.md, right: t.space.md, gap: t.space.sm, zIndex: 1000 },
  toast: {
    minHeight: t.minTapTarget,
    flexDirection: "row",
    alignItems: "center",
    gap: t.space.sm,
    paddingHorizontal: t.space.md,
    paddingVertical: t.space.sm,
    borderRadius: t.radius.md,
    backgroundColor: t.color.surfaceRaised,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: t.color.border,
    overflow: "hidden",
    ...t.elevation.overlay,
  },
  message: { flex: 1 },
}));
