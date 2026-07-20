/**
 * Tests for admin dashboard page components.
 * Uses mocked API calls and Zustand store.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AdminDashboardPage from "@/app/(admin)/dashboard/page";
import { useAuthStore } from "@/store/authStore";
import * as adminApi from "@/features/admin/api/adminApi";

jest.mock("@/features/admin/api/adminApi");
// recharts uses browser APIs not available in JSDOM; mock ResponsiveContainer
jest.mock("recharts", () => {
  const React = require("react");
  return {
    BarChart: ({ children }: { children: React.ReactNode }) => <div data-testid="bar-chart">{children}</div>,
    Bar: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container">{children}</div>
    ),
    Cell: () => null,
  };
});

const mockGetDashboard = adminApi.apiGetDashboard as jest.MockedFunction<typeof adminApi.apiGetDashboard>;
const mockListPending = adminApi.apiListPendingReview as jest.MockedFunction<typeof adminApi.apiListPendingReview>;
const mockApprove = adminApi.apiApproveRecommendation as jest.MockedFunction<typeof adminApi.apiApproveRecommendation>;
const mockReject = adminApi.apiRejectRecommendation as jest.MockedFunction<typeof adminApi.apiRejectRecommendation>;

const FAKE_DASHBOARD: adminApi.DashboardData = {
  generated_at: new Date().toISOString(),
  sources: [
    {
      id: "s1",
      type: "newsdata",
      is_active: true,
      calls_made_this_window: 42,
      quota_limit: 100,
      circuit_open: false,
      usage_pct: 42,
    },
  ],
  queue_depths: { ingestion: 5, nlp: 2, llm: 1, alerts: 0 },
  pending_review_count: 3,
  errors_last_hour: 1,
};

const FAKE_PENDING: adminApi.PendingRecommendation[] = [
  {
    id: "r1",
    story_id: "s1",
    audience: "exec",
    recommendation_text: "Consider reviewing the situation.",
    risk_level: "high",
    confidence_score: 0.55,
    generated_at: new Date().toISOString(),
  },
];

function setAdminUser(role: string = "admin") {
  useAuthStore.setState({
    user: { id: "u1", email: "admin@test.com", role, workspace_id: "ws1" },
    accessToken: "admin-token",
  });
}

beforeEach(() => {
  useAuthStore.setState({ user: null, accessToken: null });
  jest.clearAllMocks();
  mockGetDashboard.mockResolvedValue(FAKE_DASHBOARD);
  mockListPending.mockResolvedValue(FAKE_PENDING);
  mockApprove.mockResolvedValue({ id: "r1", action: "approved", audit_log_id: "al1" });
  mockReject.mockResolvedValue({ id: "r1", action: "rejected", audit_log_id: "al2" });
});

// ── Auth / role gating ─────────────────────────────────────────────────────

describe("AdminDashboardPage — access control", () => {
  it("shows sign-in prompt when unauthenticated", () => {
    render(<AdminDashboardPage />);
    expect(screen.getByText(/sign in to access/i)).toBeInTheDocument();
  });

  it("shows forbidden message for viewer role", () => {
    useAuthStore.setState({
      user: { id: "u2", email: "v@t.com", role: "viewer", workspace_id: "ws1" },
      accessToken: "tok",
    });
    render(<AdminDashboardPage />);
    expect(screen.getByText(/admin or owner role required/i)).toBeInTheDocument();
  });

  it("shows forbidden message for analyst role", () => {
    useAuthStore.setState({
      user: { id: "u3", email: "a@t.com", role: "analyst", workspace_id: "ws1" },
      accessToken: "tok",
    });
    render(<AdminDashboardPage />);
    expect(screen.getByText(/admin or owner role required/i)).toBeInTheDocument();
  });

  it("renders dashboard for admin role", async () => {
    setAdminUser("admin");
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByText("Operations Dashboard")).toBeInTheDocument(),
    );
  });

  it("renders dashboard for owner role", async () => {
    setAdminUser("owner");
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByText("Operations Dashboard")).toBeInTheDocument(),
    );
  });
});

// ── Dashboard content ──────────────────────────────────────────────────────

describe("AdminDashboardPage — content", () => {
  beforeEach(() => setAdminUser());

  it("shows pending review count", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() => expect(screen.getByText("3")).toBeInTheDocument());
  });

  it("shows errors last hour", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByText(/errors \(1h\)/i)).toBeInTheDocument(),
    );
  });

  it("shows source type name", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() => expect(screen.getByText("newsdata")).toBeInTheDocument());
  });

  it("shows queue depths chart", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() => expect(screen.getByTestId("bar-chart")).toBeInTheDocument());
  });

  it("calls apiGetDashboard on mount", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() => expect(mockGetDashboard).toHaveBeenCalledTimes(1));
  });

  it("calls apiListPendingReview on mount", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() => expect(mockListPending).toHaveBeenCalledTimes(1));
  });
});

// ── Review queue ───────────────────────────────────────────────────────────

describe("AdminDashboardPage — review queue", () => {
  beforeEach(() => setAdminUser());

  it("shows pending recommendation text", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByText("Consider reviewing the situation.")).toBeInTheDocument(),
    );
  });

  it("shows Approve button for pending rec", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /approve recommendation r1/i })).toBeInTheDocument(),
    );
  });

  it("shows Reject button for pending rec", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /reject recommendation r1/i })).toBeInTheDocument(),
    );
  });

  it("clicking Approve calls apiApproveRecommendation", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /approve recommendation r1/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /approve recommendation r1/i }));
    await waitFor(() => expect(mockApprove).toHaveBeenCalledWith("admin-token", "r1", expect.any(Function)));
  });

  it("clicking Approve removes item from queue", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByText("Consider reviewing the situation.")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /approve recommendation r1/i }));
    await waitFor(() =>
      expect(screen.queryByText("Consider reviewing the situation.")).not.toBeInTheDocument(),
    );
  });

  it("clicking Reject calls apiRejectRecommendation", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /reject recommendation r1/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /reject recommendation r1/i }));
    await waitFor(() => expect(mockReject).toHaveBeenCalledWith("admin-token", "r1", expect.any(Function)));
  });

  it("shows empty queue message when no pending recs", async () => {
    mockListPending.mockResolvedValue([]);
    render(<AdminDashboardPage />);
    await waitFor(() => expect(screen.getByText("Queue is clear")).toBeInTheDocument());
  });
});

// ── Refresh ────────────────────────────────────────────────────────────────

describe("AdminDashboardPage — refresh", () => {
  beforeEach(() => setAdminUser());

  it("has a Refresh button", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /refresh dashboard/i })).toBeInTheDocument(),
    );
  });

  it("clicking Refresh calls apiGetDashboard again", async () => {
    render(<AdminDashboardPage />);
    await waitFor(() => expect(mockGetDashboard).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /refresh dashboard/i }));
    await waitFor(() => expect(mockGetDashboard).toHaveBeenCalledTimes(2));
  });
});
