import {
  leaderAngle,
  followerAngle,
  foldBrightness,
  LEADER_MAX_ANGLE_DEG,
  FOLLOWER_HIDDEN_ANGLE_DEG,
  EDGE_DAMP,
  V_COMPLETE_THRESHOLD,
  H_COMPLETE_THRESHOLD,
} from "@/components/flip/flipMath";

// ── leaderAngle ──────────────────────────────────────────────────────────────

describe("leaderAngle", () => {
  describe("top leader (direction > 0)", () => {
    it("is 0 at progress=0", () => {
      expect(leaderAngle(0, 1, true)).toBeCloseTo(0);
    });

    it("is -LEADER_MAX at progress=0.5 (phase 1 complete)", () => {
      expect(leaderAngle(0.5, 1, true)).toBeCloseTo(-LEADER_MAX_ANGLE_DEG);
    });

    it("stays at -LEADER_MAX for progress>0.5", () => {
      expect(leaderAngle(0.75, 1, true)).toBeCloseTo(-LEADER_MAX_ANGLE_DEG);
      expect(leaderAngle(1, 1, true)).toBeCloseTo(-LEADER_MAX_ANGLE_DEG);
    });

    it("is half max at progress=0.25", () => {
      expect(leaderAngle(0.25, 1, true)).toBeCloseTo(-LEADER_MAX_ANGLE_DEG / 2);
    });
  });

  describe("bottom leader (direction < 0)", () => {
    it("is 0 at progress=0", () => {
      expect(leaderAngle(0, -1, false)).toBe(0);
    });

    it("is +LEADER_MAX at progress=0.5", () => {
      expect(leaderAngle(0.5, -1, false)).toBeCloseTo(LEADER_MAX_ANGLE_DEG);
    });

    it("stays at +LEADER_MAX for progress>0.5", () => {
      expect(leaderAngle(1, -1, false)).toBeCloseTo(LEADER_MAX_ANGLE_DEG);
    });
  });

  it("clamps progress below 0", () => {
    expect(leaderAngle(-0.5, 1, true)).toBeCloseTo(0);
  });

  it("clamps progress above 1", () => {
    expect(leaderAngle(2, 1, true)).toBeCloseTo(-LEADER_MAX_ANGLE_DEG);
  });
});

// ── followerAngle ────────────────────────────────────────────────────────────

describe("followerAngle", () => {
  describe("bottom follower (top leads, direction > 0)", () => {
    it("is +FOLLOWER_HIDDEN at progress=0 (waiting behind)", () => {
      expect(followerAngle(0, 1, false)).toBeCloseTo(FOLLOWER_HIDDEN_ANGLE_DEG);
    });

    it("stays hidden through phase 1 (progress=0.5)", () => {
      expect(followerAngle(0.5, 1, false)).toBeCloseTo(FOLLOWER_HIDDEN_ANGLE_DEG);
    });

    it("returns to 0 (flat) at progress=1", () => {
      expect(followerAngle(1, 1, false)).toBeCloseTo(0);
    });

    it("is at half the hidden angle at progress=0.75 (midway through phase 2)", () => {
      expect(followerAngle(0.75, 1, false)).toBeCloseTo(FOLLOWER_HIDDEN_ANGLE_DEG / 2);
    });
  });

  describe("top follower", () => {
    it("is -FOLLOWER_HIDDEN at progress=0", () => {
      expect(followerAngle(0, -1, true)).toBeCloseTo(-FOLLOWER_HIDDEN_ANGLE_DEG);
    });

    it("returns to 0 at progress=1", () => {
      expect(followerAngle(1, -1, true)).toBeCloseTo(0);
    });
  });

  it("clamps progress below 0", () => {
    expect(followerAngle(-1, 1, false)).toBeCloseTo(FOLLOWER_HIDDEN_ANGLE_DEG);
  });

  it("clamps progress above 1", () => {
    expect(followerAngle(2, 1, false)).toBeCloseTo(0);
  });
});

// ── foldBrightness ───────────────────────────────────────────────────────────

describe("foldBrightness", () => {
  it("is 1.0 at 0°", () => {
    expect(foldBrightness(0)).toBe(1);
  });

  it("is 0.65 at LEADER_MAX_ANGLE_DEG (fully folded)", () => {
    expect(foldBrightness(LEADER_MAX_ANGLE_DEG)).toBeCloseTo(0.65);
  });

  it("is 0.65 beyond LEADER_MAX_ANGLE_DEG (capped)", () => {
    expect(foldBrightness(180)).toBeCloseTo(0.65);
  });

  it("works with negative angles (symmetric)", () => {
    expect(foldBrightness(-LEADER_MAX_ANGLE_DEG)).toBeCloseTo(0.65);
    expect(foldBrightness(-45)).toBeCloseTo(foldBrightness(45));
  });

  it("interpolates linearly at half max angle", () => {
    const halfAngle = LEADER_MAX_ANGLE_DEG / 2;
    expect(foldBrightness(halfAngle)).toBeCloseTo(0.825);
  });
});

// ── constants ────────────────────────────────────────────────────────────────

describe("constants", () => {
  it("EDGE_DAMP is 0.25 (25% damping at boundaries)", () => {
    expect(EDGE_DAMP).toBe(0.25);
  });

  it("V_COMPLETE_THRESHOLD is 0.5 (commit after 50% drag)", () => {
    expect(V_COMPLETE_THRESHOLD).toBe(0.5);
  });

  it("H_COMPLETE_THRESHOLD is 0.45 (commit after 45% drag)", () => {
    expect(H_COMPLETE_THRESHOLD).toBe(0.45);
  });
});

// ── phase boundary integration ───────────────────────────────────────────────

describe("two-phase animation invariants", () => {
  it("leader reaches hidden position exactly when follower starts moving (p=0.5)", () => {
    const leaderAtMidpoint = leaderAngle(0.5, 1, true);
    const followerAtMidpoint = followerAngle(0.5, 1, false);
    // Leader is at full hidden angle; follower is still at its hidden angle
    expect(Math.abs(leaderAtMidpoint)).toBeCloseTo(LEADER_MAX_ANGLE_DEG);
    expect(Math.abs(followerAtMidpoint)).toBeCloseTo(FOLLOWER_HIDDEN_ANGLE_DEG);
  });

  it("both flaps are near-flat at progress=1 (card fully flipped)", () => {
    const leader = leaderAngle(1, 1, true);
    const follower = followerAngle(1, 1, false);
    // Leader stays at hidden; follower is at 0 (folded flat from below)
    expect(Math.abs(leader)).toBeCloseTo(LEADER_MAX_ANGLE_DEG); // stays hidden
    expect(Math.abs(follower)).toBeCloseTo(0);
  });
});
