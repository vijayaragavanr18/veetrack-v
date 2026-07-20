/**
 * Component tests for WatchlistToggle.
 *
 * The component only renders for authenticated analyst/admin/owner users.
 * It calls apiCreateWatchlist / apiDeleteWatchlist via the store.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import WatchlistToggle from "@/components/ui/WatchlistToggle";
import { useAuthStore } from "@/store/authStore";
import { useWatchlistStore } from "@/features/watchlists/store/useWatchlistStore";
import * as watchlistsApi from "@/features/watchlists/api/watchlistsApi";
import type { WatchlistItem } from "@/features/watchlists/api/watchlistsApi";

jest.mock("@/features/watchlists/api/watchlistsApi");

const mockCreate = watchlistsApi.apiCreateWatchlist as jest.MockedFunction<
  typeof watchlistsApi.apiCreateWatchlist
>;
const mockDelete = watchlistsApi.apiDeleteWatchlist as jest.MockedFunction<
  typeof watchlistsApi.apiDeleteWatchlist
>;

const FAKE_ITEM: WatchlistItem = {
  id: "wl1",
  workspace_id: "ws1",
  user_id: "u1",
  entity_id: "e1",
  alert_channels: { websocket: true },
};

function setAnalystUser() {
  useAuthStore.setState({
    user: { id: "u1", email: "a@test.com", role: "analyst", workspace_id: "ws1" },
    accessToken: "tok-analyst",
  });
}

function setViewerUser() {
  useAuthStore.setState({
    user: { id: "u2", email: "v@test.com", role: "viewer", workspace_id: "ws1" },
    accessToken: "tok-viewer",
  });
}

beforeEach(() => {
  useAuthStore.setState({ user: null, accessToken: null });
  useWatchlistStore.setState({ watchlists: [], watchedEntityIds: new Set() });
  jest.clearAllMocks();
});

// ── Visibility ────────────────────────────────────────────────────────────

describe("WatchlistToggle — visibility", () => {
  it("renders nothing when user is unauthenticated", () => {
    const { container } = render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for viewer role", () => {
    setViewerUser();
    const { container } = render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders for analyst role", () => {
    setAnalystUser();
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("renders for admin role", () => {
    useAuthStore.setState({
      user: { id: "u3", email: "adm@test.com", role: "admin", workspace_id: "ws1" },
      accessToken: "tok-admin",
    });
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });
});

// ── Unwatched state ───────────────────────────────────────────────────────

describe("WatchlistToggle — unwatched", () => {
  beforeEach(() => setAnalystUser());

  it("shows 'Watch' label", () => {
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    expect(screen.getByText("Watch")).toBeInTheDocument();
  });

  it("aria-pressed is false", () => {
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "false");
  });

  it("aria-label includes entity name", () => {
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    expect(screen.getByRole("button")).toHaveAccessibleName(/Watch Tesla/i);
  });
});

// ── Watched state ─────────────────────────────────────────────────────────

describe("WatchlistToggle — watched", () => {
  beforeEach(() => {
    setAnalystUser();
    useWatchlistStore.getState().setWatchlists([FAKE_ITEM]);
  });

  it("shows 'Watching' label", () => {
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    expect(screen.getByText("Watching")).toBeInTheDocument();
  });

  it("aria-pressed is true", () => {
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });
});

// ── Add to watchlist ──────────────────────────────────────────────────────

describe("WatchlistToggle — adding", () => {
  beforeEach(() => {
    setAnalystUser();
    mockCreate.mockResolvedValue(FAKE_ITEM);
  });

  it("calls apiCreateWatchlist when clicking Watch", async () => {
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    expect(mockCreate).toHaveBeenCalledWith(
      "tok-analyst",
      { entity_id: "e1", alert_channels: { websocket: true } },
      expect.any(Function),
    );
  });

  it("shows 'Watching' after successful add", async () => {
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByText("Watching")).toBeInTheDocument());
  });
});

// ── Remove from watchlist ─────────────────────────────────────────────────

describe("WatchlistToggle — removing", () => {
  beforeEach(() => {
    setAnalystUser();
    useWatchlistStore.getState().setWatchlists([FAKE_ITEM]);
    mockDelete.mockResolvedValue(undefined);
  });

  it("calls apiDeleteWatchlist when clicking Watching", async () => {
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledTimes(1));
    expect(mockDelete).toHaveBeenCalledWith("tok-analyst", "wl1", expect.any(Function));
  });

  it("shows 'Watch' after successful removal", async () => {
    render(<WatchlistToggle entityId="e1" entityName="Tesla" />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByText("Watch")).toBeInTheDocument());
  });
});
