/**
 * Wording for live-data states that no board shows. Plain, in the boards' voice
 * ("We could not reach BNR today"). Every line here is listed for design review.
 */
export const COPY = {
  loadingTitle: 'Loading',
  loadingBody: 'This usually takes a moment.',
  refreshingTitle: 'Checking for changes',
  refreshingBody: 'The list below stays on screen meanwhile.',
  unreachableTitle: 'We could not reach Blackkite just now',
  unreachableBody: 'Check your connection, then try again. Nothing you saved is lost.',
  /** Shown when an action did not reach the server and was undone on screen. */
  actionFailed: 'We could not reach Blackkite just now, so that change was undone. Try again.',
  tryAgain: 'Try again',
} as const;
