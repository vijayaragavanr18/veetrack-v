/**
 * Pure, unit-testable math for the half-bend 3D flip animation.
 *
 * Architecture mirrors the reference HTML's updateVerticalFlip():
 * progress is a 0..1 scalar; phase 0→0.5 rotates the leader to hidden;
 * phase 0.5→1 rotates the follower from hidden to flat.
 */

/** Degrees to which the leader half rotates before it is fully hidden. */
export const LEADER_MAX_ANGLE_DEG = 95;

/** Start-angle at which the follower half sits while waiting to fold in. */
export const FOLLOWER_HIDDEN_ANGLE_DEG = 100;

/** Maximum damping factor applied when no valid navigation target exists. */
export const EDGE_DAMP = 0.25;

/**
 * Returns the current rotateX/Y angle for the leader half given progress 0..1.
 *
 * @param progress   0 = idle, 1 = fully flipped
 * @param direction  +1 = forward (down/right), -1 = backward (up/left)
 * @param isLeaderTop  true when the top half leads (direction > 0, vertical axis)
 */
export function leaderAngle(
  progress: number,
  direction: number,
  isLeaderTop: boolean,
): number {
  const p = Math.max(0, Math.min(1, progress));
  const sign = isLeaderTop ? -1 : 1; // top panel rotates negative (away from viewer)
  if (p <= 0.5) {
    return sign * LEADER_MAX_ANGLE_DEG * (p / 0.5);
  }
  return sign * LEADER_MAX_ANGLE_DEG;
}

/**
 * Returns the current rotateX/Y angle for the follower half given progress 0..1.
 *
 * @param isFollowerTop  true when the top half is the follower
 */
export function followerAngle(
  progress: number,
  _direction: number,
  isFollowerTop: boolean,
): number {
  const p = Math.max(0, Math.min(1, progress));
  const sign = isFollowerTop ? -1 : 1;
  if (p <= 0.5) {
    return sign * FOLLOWER_HIDDEN_ANGLE_DEG;
  }
  const t = (p - 0.5) / 0.5;
  return sign * FOLLOWER_HIDDEN_ANGLE_DEG * (1 - t);
}

/**
 * Brightness multiplier (0..1) representing the fold shadow as the half rotates.
 * Matches reference: `1 - Math.min(Math.abs(angle) / 95, 1) * 0.35`
 */
export function foldBrightness(angleDeg: number): number {
  return 1 - Math.min(Math.abs(angleDeg) / LEADER_MAX_ANGLE_DEG, 1) * 0.35;
}

/** Progress distance to trigger completion — vertical axis (75% of card height). */
export const V_COMPLETE_THRESHOLD = 0.5;
/** Progress distance to trigger completion — horizontal axis (45% of card width). */
export const H_COMPLETE_THRESHOLD = 0.45;
