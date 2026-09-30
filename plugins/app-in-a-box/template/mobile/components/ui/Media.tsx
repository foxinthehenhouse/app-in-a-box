/**
 * Media: an image with an honest placeholder, on expo-image (disk + memory cache,
 * no flicker when the source changes, BlurHash/ThumbHash placeholders, a native
 * cross-fade). It is the prototype's `image` block: until a real `source` exists
 * it shows the themed placeholder with its label, exactly like the prototype.
 *
 * `ratio` is "W:H" ("3:4" for a book cover, "16:9" for a photo). Pass a
 * `placeholder` hash from your API for a blurred preview while the image loads.
 * The cross-fade uses the motion tokens, and reduce motion turns it off.
 */
import { View } from "react-native";
import { Image, type ImageSource } from "expo-image";

import { useReducedMotion } from "../../lib/motion";
import { makeStyles, motion, useTheme } from "../../lib/theme";
import { Icon } from "./Icon";
import { Meta } from "./Text";

export interface MediaProps {
  /** What the image shows, for screen readers (and the placeholder's caption). */
  label: string;
  source?: ImageSource | string | null;
  /** BlurHash / ThumbHash string shown while `source` loads. */
  placeholder?: string;
  ratio?: `${number}:${number}`;
  testID?: string;
}

/** "3:4" -> 0.75; anything malformed falls back to 4:3. Pure for tests. */
export function aspect(ratio: string | undefined): number {
  const [w = 0, h = 0] = (ratio ?? "4:3").split(":").map(Number);
  return w > 0 && h > 0 ? w / h : 4 / 3;
}

export function Media({ label, source, placeholder, ratio, testID }: MediaProps) {
  const t = useTheme();
  const s = useStyles();
  const reduced = useReducedMotion();
  const box = [s.box, { aspectRatio: aspect(ratio) }];
  if (!source) {
    return (
      <View style={box} accessible accessibilityRole="image" accessibilityLabel={label} testID={testID}>
        <Icon sf="photo" md="image" size={28} color="inkFaint" />
        <Meta style={s.caption}>{label}</Meta>
      </View>
    );
  }
  return (
    <Image
      source={source}
      placeholder={placeholder ? { blurhash: placeholder } : undefined}
      contentFit="cover"
      transition={reduced ? 0 : { duration: motion.duration.standard, effect: "cross-dissolve" }}
      accessible
      accessibilityLabel={label}
      style={[box, { backgroundColor: t.color.control }]}
      testID={testID}
    />
  );
}

const useStyles = makeStyles((t) => ({
  box: {
    width: "100%",
    borderRadius: t.radius.lg,
    overflow: "hidden",
    backgroundColor: t.color.control,
    borderWidth: 1,
    borderColor: t.color.border,
    alignItems: "center",
    justifyContent: "center",
    gap: t.space.sm,
  },
  caption: { textAlign: "center" },
}));
