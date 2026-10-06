/**
 * ImageUpload (added by the recipe-uploads skill): choose a photo, watch it upload,
 * retry if it fails.
 *
 *   <ImageUpload onUploaded={(u) => attach(u.id)} testID="entry-photo" />
 *
 * The preview is the photo on the device, so it shows at once; the progress bar is
 * announced as a progress bar with a percentage; a failure says what happened and
 * offers "Try again", which resumes from the step that failed (lib/uploads.ts).
 */
import { useEffect } from "react";
import { AccessibilityInfo, View } from "react-native";

import { useT } from "../../lib/i18n";
import { makeStyles } from "../../lib/theme";
import { type Upload, useImageUpload } from "../../lib/uploads";
import { Button } from "./Button";
import { ErrorNotice } from "./ErrorNotice";
import { ProgressBar } from "./Feedback";
import { Media } from "./Media";
import { Meta } from "./Text";

export interface ImageUploadProps {
  onUploaded?: (upload: Upload) => void;
  testID?: string;
}

export function ImageUpload({ onUploaded, testID = "image-upload" }: ImageUploadProps) {
  const t = useT();
  const s = useStyles();
  const { state, pick, retry } = useImageUpload({ onUploaded });

  useEffect(() => {
    if (state.status === "done") AccessibilityInfo.announceForAccessibility(t("uploads.uploaded"));
  }, [state.status, t]);

  return (
    <View style={s.wrap} testID={testID}>
      {state.image ? <Media label={t("uploads.preview")} source={state.image.uri} ratio="4:3" testID={`${testID}-preview`} /> : null}
      {state.status === "uploading" ? (
        <View style={s.progress}>
          <ProgressBar value={state.progress} label={t("uploads.uploading")} testID={`${testID}-progress`} />
          <Meta>{t("uploads.uploading")}</Meta>
        </View>
      ) : null}
      {state.status === "done" ? <Meta testID={`${testID}-done`}>{t("uploads.uploaded")}</Meta> : null}
      {state.status === "error" && state.error ? (
        <ErrorNotice
          message={state.error}
          reference={state.errorRef}
          onRetry={state.canRetry ? () => void retry() : undefined}
          testID={`${testID}-error`}
        />
      ) : null}
      {state.status !== "uploading" ? (
        <Button
          label={state.image ? t("uploads.chooseAnother") : t("uploads.choose")}
          accessibilityLabel={t("uploads.chooseLabel")}
          variant={state.image ? "secondary" : "primary"}
          icon={{ sf: "photo.on.rectangle", md: "add_photo_alternate" }}
          onPress={() => void pick()}
          testID={`${testID}-choose-button`}
        />
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: t.space.md },
  progress: { gap: t.space.xs },
}));
