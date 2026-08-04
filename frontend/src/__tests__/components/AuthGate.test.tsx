import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AuthGate } from "@/components/auth/AuthGate";
import { api } from "@/lib/api";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/api", () => ({
  AUTH_REQUIRED_EVENT: "exam-review:auth-required",
  api: {
    auth: {
      me: vi.fn(),
      refresh: vi.fn(),
    },
  },
}));

describe("AuthGate", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.mocked(api.auth.me).mockReset();
    vi.mocked(api.auth.refresh).mockReset();
  });

  it("shows the workspace for an active session", async () => {
    vi.mocked(api.auth.me).mockResolvedValue({} as never);

    render(<AuthGate>workspace</AuthGate>);

    expect(await screen.findByText("workspace")).toBeInTheDocument();
    expect(api.auth.refresh).not.toHaveBeenCalled();
  });

  it("recovers an expired access cookie through refresh", async () => {
    vi.mocked(api.auth.me).mockRejectedValue(new Error("expired"));
    vi.mocked(api.auth.refresh).mockResolvedValue({} as never);

    render(<AuthGate>workspace</AuthGate>);

    expect(await screen.findByText("workspace")).toBeInTheDocument();
    expect(api.auth.refresh).toHaveBeenCalledOnce();
  });

  it("redirects when the session cannot be recovered", async () => {
    vi.mocked(api.auth.me).mockRejectedValue(new Error("missing"));
    vi.mocked(api.auth.refresh).mockRejectedValue(new Error("missing"));

    render(<AuthGate>workspace</AuthGate>);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("workspace")).not.toBeInTheDocument();
  });

  it("redirects when an active request reports an unrecoverable session", async () => {
    vi.mocked(api.auth.me).mockResolvedValue({} as never);
    render(<AuthGate>workspace</AuthGate>);
    expect(await screen.findByText("workspace")).toBeInTheDocument();

    window.dispatchEvent(new Event("exam-review:auth-required"));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
