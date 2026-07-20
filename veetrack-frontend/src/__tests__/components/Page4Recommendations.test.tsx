/**
 * Component tests for Page4Recommendations — confident items, pending-review
 * items, empty state, RBAC toggle, RiskBadge, ConfidenceIndicator.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import Page4Recommendations from "@/components/pages/Page4Recommendations";
import { useAuthStore } from "@/store/authStore";
import { MOCK_STORIES } from "@/lib/mock-data";
import type { MockStory, MockRecommendation } from "@/types";

// ── helpers ───────────────────────────────────────────────────────────────

const story = MOCK_STORIES[0]; // Tesla — 1 confident + 1 needs_human_review

const storyNoRecs: MockStory = { ...story, recommendations: [] };

function makeRec(overrides: Partial<MockRecommendation> & { id: string }): MockRecommendation {
  return {
    id: overrides.id,
    recommendation_text: overrides.recommendation_text ?? "Consider monitoring press coverage.",
    audience: overrides.audience ?? "pr",
    risk_level: overrides.risk_level ?? "medium",
    confidence_score: overrides.confidence_score ?? 0.85,
    needs_human_review: overrides.needs_human_review ?? false,
  };
}

const confidentOnly: MockStory = {
  ...story,
  recommendations: [makeRec({ id: "r1", confidence_score: 0.9 })],
};

const mixedStory: MockStory = {
  ...story,
  recommendations: [
    makeRec({ id: "r3", confidence_score: 0.92, recommendation_text: "Confident action." }),
    makeRec({ id: "r4", confidence_score: 0.45, needs_human_review: true, recommendation_text: "Uncertain action." }),
  ],
};

function setRole(role: string | null) {
  if (role === null) {
    useAuthStore.setState({ user: null });
  } else {
    useAuthStore.setState({
      user: { id: "u1", email: "test@test.com", role, workspace_id: "ws1" },
    });
  }
}

beforeEach(() => {
  // Reset to unauthenticated
  useAuthStore.setState({ user: null });
});

// ── Empty state ────────────────────────────────────────────────────────────

describe("Page4Recommendations — empty state", () => {
  it("renders the empty state heading", () => {
    render(<Page4Recommendations story={storyNoRecs} />);
    expect(screen.getByText(/No recommendations generated yet/i)).toBeInTheDocument();
  });

  it("renders the empty state description", () => {
    render(<Page4Recommendations story={storyNoRecs} />);
    expect(screen.getByText(/analysis pipeline completes/i)).toBeInTheDocument();
  });

  it("still renders the Recommendations heading in empty state", () => {
    render(<Page4Recommendations story={storyNoRecs} />);
    expect(screen.getByText("Recommendations")).toBeInTheDocument();
  });
});

// ── Confident recommendations ─────────────────────────────────────────────

describe("Page4Recommendations — confident recommendations", () => {
  it("renders the recommendation text", () => {
    render(<Page4Recommendations story={story} />);
    expect(screen.getByText(story.recommendations[0].recommendation_text)).toBeInTheDocument();
  });

  it("renders the audience label 'PR Team'", () => {
    render(<Page4Recommendations story={story} />);
    expect(screen.getByText("PR Team")).toBeInTheDocument();
  });

  it("renders the risk badge for the confident rec", () => {
    render(<Page4Recommendations story={confidentOnly} />);
    expect(screen.getByLabelText(/Risk level: MEDIUM/i)).toBeInTheDocument();
  });

  it("renders a confidence indicator", () => {
    render(<Page4Recommendations story={confidentOnly} />);
    expect(screen.getByRole("meter")).toBeInTheDocument();
  });

  it("does not show 'Needs Review' on a confident rec", () => {
    render(<Page4Recommendations story={confidentOnly} />);
    expect(screen.queryByText("Needs Review")).not.toBeInTheDocument();
  });

  it("advisory disclaimer is present", () => {
    render(<Page4Recommendations story={confidentOnly} />);
    expect(screen.getByText(/advisory only/i)).toBeInTheDocument();
  });
});

// ── Pending-review recommendations ────────────────────────────────────────

describe("Page4Recommendations — pending-review items (unauthenticated)", () => {
  it("shows pending-review text when unauthenticated (showPendingReview defaults open)", () => {
    render(<Page4Recommendations story={story} />);
    // rec-002 has needs_human_review: true — shown by default for unauthenticated
    expect(screen.getByText("Needs Review")).toBeInTheDocument();
  });

  it("shows the 'Below confidence threshold' warning", () => {
    render(<Page4Recommendations story={story} />);
    expect(screen.getByText(/Below confidence threshold/i)).toBeInTheDocument();
  });

  it("renders a confidence indicator for the pending rec too", () => {
    render(<Page4Recommendations story={story} />);
    // 2 recs → 2 meters
    expect(screen.getAllByRole("meter")).toHaveLength(2);
  });
});

// ── RBAC: viewer role ─────────────────────────────────────────────────────

describe("Page4Recommendations — viewer role", () => {
  beforeEach(() => setRole("viewer"));

  it("does NOT render the toggle button", () => {
    render(<Page4Recommendations story={mixedStory} />);
    expect(screen.queryByRole("button", { name: /pending-review/i })).not.toBeInTheDocument();
  });

  it("does NOT render pending-review recommendation text", () => {
    render(<Page4Recommendations story={mixedStory} />);
    expect(screen.queryByText("Uncertain action.")).not.toBeInTheDocument();
  });

  it("does NOT render 'Needs Review' badge", () => {
    render(<Page4Recommendations story={mixedStory} />);
    expect(screen.queryByText("Needs Review")).not.toBeInTheDocument();
  });

  it("DOES render the confident recommendation", () => {
    render(<Page4Recommendations story={mixedStory} />);
    expect(screen.getByText("Confident action.")).toBeInTheDocument();
  });
});

// ── RBAC: analyst role ────────────────────────────────────────────────────

describe("Page4Recommendations — analyst role", () => {
  beforeEach(() => setRole("analyst"));

  it("renders the toggle button", () => {
    render(<Page4Recommendations story={mixedStory} />);
    expect(
      screen.getByRole("button", { name: /pending-review suggestion/i }),
    ).toBeInTheDocument();
  });

  it("pending items are hidden by default for analyst", () => {
    render(<Page4Recommendations story={mixedStory} />);
    expect(screen.queryByText("Uncertain action.")).not.toBeInTheDocument();
  });

  it("clicking the toggle reveals pending items", () => {
    render(<Page4Recommendations story={mixedStory} />);
    const toggle = screen.getByRole("button", { name: /pending-review suggestion/i });
    fireEvent.click(toggle);
    expect(screen.getByText("Uncertain action.")).toBeInTheDocument();
  });

  it("clicking the toggle again hides pending items", () => {
    render(<Page4Recommendations story={mixedStory} />);
    const toggle = screen.getByRole("button", { name: /pending-review suggestion/i });
    fireEvent.click(toggle); // open
    fireEvent.click(toggle); // close
    expect(screen.queryByText("Uncertain action.")).not.toBeInTheDocument();
  });

  it("toggle has correct aria-expanded state", () => {
    render(<Page4Recommendations story={mixedStory} />);
    const toggle = screen.getByRole("button", { name: /pending-review suggestion/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("'Needs Review' badge appears after expanding", () => {
    render(<Page4Recommendations story={mixedStory} />);
    const toggle = screen.getByRole("button", { name: /pending-review suggestion/i });
    fireEvent.click(toggle);
    expect(screen.getByText("Needs Review")).toBeInTheDocument();
  });
});

// ── RBAC: admin and owner ─────────────────────────────────────────────────

describe("Page4Recommendations — admin role", () => {
  it("admin can also see the toggle", () => {
    setRole("admin");
    render(<Page4Recommendations story={mixedStory} />);
    expect(
      screen.getByRole("button", { name: /pending-review suggestion/i }),
    ).toBeInTheDocument();
  });
});

describe("Page4Recommendations — owner role", () => {
  it("owner can also see the toggle", () => {
    setRole("owner");
    render(<Page4Recommendations story={mixedStory} />);
    expect(
      screen.getByRole("button", { name: /pending-review suggestion/i }),
    ).toBeInTheDocument();
  });
});

// ── RiskBadge and ConfidenceIndicator ─────────────────────────────────────

describe("Page4Recommendations — RiskBadge", () => {
  it("renders CRITICAL risk badge for a critical rec", () => {
    const s: MockStory = {
      ...story,
      recommendations: [makeRec({ id: "rx", risk_level: "critical" })],
    };
    render(<Page4Recommendations story={s} />);
    expect(screen.getByLabelText(/Risk level: CRITICAL/i)).toBeInTheDocument();
  });

  it("renders LOW risk badge for a low risk rec", () => {
    const s: MockStory = {
      ...story,
      recommendations: [makeRec({ id: "ry", risk_level: "low" })],
    };
    render(<Page4Recommendations story={s} />);
    expect(screen.getByLabelText(/Risk level: LOW/i)).toBeInTheDocument();
  });
});

describe("Page4Recommendations — ConfidenceIndicator", () => {
  it("shows the correct percentage for a 90% confidence rec", () => {
    const s: MockStory = {
      ...story,
      recommendations: [makeRec({ id: "rz", confidence_score: 0.9 })],
    };
    render(<Page4Recommendations story={s} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "90");
  });
});
