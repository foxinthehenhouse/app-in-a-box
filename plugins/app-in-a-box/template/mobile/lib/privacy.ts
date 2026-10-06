/**
 * The runtime half of the privacy lints: whatever slips past review is still stripped
 * before it leaves the phone.
 *
 * scripts/check_guardrails.py fails CI on an analytics payload or a log call that
 * carries personal data (email, name, phone, precise location, free text, credentials,
 * birth date, and health, money or biometric values). These scrubbers apply the same
 * idea at runtime to every PostHog event (lib/analytics.ts) and Sentry event
 * (lib/monitoring.ts), by key name. They are always on, whichever packs are enabled: a
 * key lookup per property costs nothing, and none of these values belong in either tool.
 *
 * Tested in lib/__tests__/privacy.test.ts. Keep SENSITIVE_KEY in step with `PII` in
 * scripts/check_guardrails.py (tests/test_guardrails.py checks a sample of each).
 */

type Scalar = string | number | boolean | null;

/** Matched against the key in snake_case words (`userEmail` -> `user_email`). */
export const SENSITIVE_KEY = new RegExp(
  [
    "(^|_)e_?mail(_|$)",
    "(^|_)(phone|phone_number|mobile_number|msisdn)(_|$)",
    "^(first|last|full|display|real|given|family|legal|middle|user|nick|sur)_?name$",
    "(^|_)(address|street|postcode|postal_code|zip|zipcode|zip_code)(_|$)",
    "(^|_)(lat|lng|lon|latitude|longitude|coords?|coordinates|geohash)(_|$)",
    "(^|_)(text|body|message|comment|comments|note|notes|query|search_term|content|caption|bio|description|transcript|prompt|reply)(_|$)",
    "(^|_)(password|passcode|secret|token|otp|api_key|jwt|cookie)(_|$)",
    "(^|_)(dob|birth|birthday|birthdate|date_of_birth|age|birth_year)(_|$)",
    // health
    "(^|_)(weight|height|bmi|heart_rate|hrv|bpm|blood|glucose|blood_pressure|symptoms?|diagnos[ie]s|medications?|medical|vitals?|spo2|sleep|menstrual|pregnan(cy|t)|mood|calories|body_fat|allerg(y|ies))(_|$)",
    // financial
    "(^|_)(amount|balance|iban|account_number|card|card_number|pan|cvv|cvc|routing_number|sort_code|bsb|salary|income|merchant|net_worth)(_|$)",
    // biometric
    "(^|_)(face|faceprint|face_id|face_embedding|fingerprint|voiceprint|iris|retina|biometrics?|palm)(_|$)",
  ].join("|"),
);

function snake(key: string): string {
  return key.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
}

/** A measure of the value, or a yes/no about it, is not the value (`query_length`, `has_email`). */
const MEASURE = /(^(has|is)_|_(count|length|len|size|chars|words|ms|total|bucket)$)/;

export function isSensitiveKey(key: string): boolean {
  const k = snake(key);
  return !MEASURE.test(k) && SENSITIVE_KEY.test(k);
}

/** A copy of `props` without any sensitive key. Never throws, never mutates. */
export function scrubProps(props: Record<string, Scalar>): Record<string, Scalar> {
  const out: Record<string, Scalar> = {};
  for (const [key, value] of Object.entries(props)) if (!isSensitiveKey(key)) out[key] = value;
  return out;
}

/** Sentry's event, the parts this scrubber touches. */
export interface ScrubbableEvent {
  user?: unknown;
  request?: unknown;
  extra?: Record<string, unknown>;
  tags?: Record<string, unknown>;
  contexts?: Record<string, unknown>;
  breadcrumbs?: { data?: Record<string, unknown>; message?: string }[];
}

/** Deletes sensitive keys in place (Sentry hands beforeSend its own event to edit). */
function dropSensitive(obj: Record<string, unknown> | undefined): void {
  if (!obj) return;
  for (const key of Object.keys(obj)) if (isSensitiveKey(key)) delete obj[key];
}

/**
 * Sentry `beforeSend`: no user, no request (bodies and query strings carry form input),
 * and no sensitive key in extra, tags, contexts or breadcrumb data. Breadcrumb messages
 * go too: console breadcrumbs repeat whatever was logged. The stack trace stays.
 */
export function scrubSentryEvent<E extends ScrubbableEvent>(event: E): E {
  delete event.user;
  delete event.request;
  dropSensitive(event.extra);
  dropSensitive(event.tags);
  dropSensitive(event.contexts);
  for (const crumb of event.breadcrumbs ?? []) {
    delete crumb.message;
    dropSensitive(crumb.data);
  }
  return event;
}
