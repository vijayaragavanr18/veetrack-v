/**
 * Component tests for ExportBriefButton.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ExportBriefButton from "@/components/ui/ExportBriefButton";
import { useAuthStore } from "@/store/authStore";
import * as exportsApi from "@/features/feed/api/exportsApi";

jest.mock("@/features/feed/api/exportsApi");

const mockApiExport = exportsApi.apiExportBrief as jest.MockedFunction<
  typeof exportsApi.apiExportBrief
>;
const mockDownload = exportsApi.downloadBlob as jest.MockedFunction<
  typeof exportsApi.downloadBlob
>;

function setUser(role: string = "analyst") {
  useAuthStore.setState({
    user: { id: "u1", email: "a@test.com", role, workspace_id: "ws1" },
    accessToken: "test-token",
  });
}

beforeEach(() => {
  useAuthStore.setState({ user: null, accessToken: null });
  jest.clearAllMocks();
  mockDownload.mockImplementation(() => {});
});

// ── Visibility ─────────────────────────────────────────────────────────────

describe("ExportBriefButton — visibility", () => {
  it("renders nothing when unauthenticated", () => {
    const { container } = render(<ExportBriefButton entity="Tesla" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders for authenticated user", () => {
    setUser();
    render(<ExportBriefButton entity="Tesla" />);
    expect(screen.getByRole("button", { name: /export executive brief/i })).toBeInTheDocument();
  });
});

// ── Dropdown ───────────────────────────────────────────────────────────────

describe("ExportBriefButton — dropdown", () => {
  beforeEach(() => setUser());

  it("opens dropdown on click", () => {
    render(<ExportBriefButton entity="Tesla" />);
    fireEvent.click(screen.getByRole("button", { name: /export executive brief/i }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
  });

  it("shows PDF and PPT options", () => {
    render(<ExportBriefButton entity="Tesla" />);
    fireEvent.click(screen.getByRole("button", { name: /export executive brief/i }));
    expect(screen.getByRole("menuitem", { name: /export pdf/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /export ppt/i })).toBeInTheDocument();
  });

  it("closes dropdown on second click", () => {
    render(<ExportBriefButton entity="Tesla" />);
    const trigger = screen.getByRole("button", { name: /export executive brief/i });
    fireEvent.click(trigger);
    fireEvent.click(trigger);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

// ── Exporting ──────────────────────────────────────────────────────────────

describe("ExportBriefButton — export actions", () => {
  beforeEach(() => {
    setUser();
    mockApiExport.mockResolvedValue({
      blob: new Blob(["fake pdf"], { type: "application/pdf" }),
      filename: "veetrack_brief_tesla.pdf",
    });
  });

  it("calls apiExportBrief with PDF format", async () => {
    render(<ExportBriefButton entity="Tesla" />);
    fireEvent.click(screen.getByRole("button", { name: /export executive brief/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /export pdf/i }));
    await waitFor(() => expect(mockApiExport).toHaveBeenCalledTimes(1));
    // wait for loading state to clear
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /export executive brief/i })).not.toBeDisabled(),
    );
    expect(mockApiExport).toHaveBeenCalledWith(
      "test-token",
      expect.objectContaining({ entity: "Tesla", format: "pdf" }),
    );
  });

  it("calls apiExportBrief with PPTX format", async () => {
    mockApiExport.mockResolvedValue({
      blob: new Blob(["fake pptx"], { type: "application/vnd.ms-powerpoint" }),
      filename: "veetrack_brief_tesla.pptx",
    });
    render(<ExportBriefButton entity="Tesla" />);
    fireEvent.click(screen.getByRole("button", { name: /export executive brief/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /export ppt/i }));
    await waitFor(() => expect(mockApiExport).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /export executive brief/i })).not.toBeDisabled(),
    );
    expect(mockApiExport).toHaveBeenCalledWith(
      "test-token",
      expect.objectContaining({ format: "pptx" }),
    );
  });

  it("calls downloadBlob after successful export", async () => {
    render(<ExportBriefButton entity="Tesla" />);
    fireEvent.click(screen.getByRole("button", { name: /export executive brief/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /export pdf/i }));
    await waitFor(() => expect(mockDownload).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /export executive brief/i })).not.toBeDisabled(),
    );
    expect(mockDownload).toHaveBeenCalledWith(
      expect.any(Blob),
      "veetrack_brief_tesla.pdf",
    );
  });

  it("shows loading text while exporting", async () => {
    let resolve: (v: { blob: Blob; filename: string }) => void;
    mockApiExport.mockReturnValue(new Promise((res) => { resolve = res; }));
    render(<ExportBriefButton entity="Tesla" />);
    fireEvent.click(screen.getByRole("button", { name: /export executive brief/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /export pdf/i }));
    expect(await screen.findByText(/Exporting PDF/i)).toBeInTheDocument();
    resolve!({ blob: new Blob(), filename: "f.pdf" });
  });
});

// ── Error handling ─────────────────────────────────────────────────────────

describe("ExportBriefButton — error", () => {
  beforeEach(() => setUser());

  it("shows error message on failure", async () => {
    mockApiExport.mockRejectedValue(new Error("Server unavailable"));
    render(<ExportBriefButton entity="Tesla" />);
    fireEvent.click(screen.getByRole("button", { name: /export executive brief/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /export pdf/i }));
    await waitFor(() =>
      expect(screen.getByText("Server unavailable")).toBeInTheDocument(),
    );
    // wait for loading to clear so act() is satisfied
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /export executive brief/i })).not.toBeDisabled(),
    );
  });
});
