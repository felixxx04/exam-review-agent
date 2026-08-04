import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";

describe("auth api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie = "csrf_token=csrf-test-token";
  });

  it("sends credentials and returns the authenticated user on login", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          data: {
            user: { id: 1, username: "student", role: "user" },
            access_expires_at: "2026-08-04T00:00:00Z",
            refresh_expires_at: "2026-09-03T00:00:00Z",
          },
          error: null,
          meta: null,
        }),
        { status: 200 },
      ),
    );

    const result = await api.auth.login("student", "Student-pass-123");

    expect(result.user.username).toBe("student");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/auth/login"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
      }),
    );
  });

  it("adds the double-submit CSRF header to cookie-authenticated mutations", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({ success: true, data: {}, error: null, meta: null }),
          { status: 200 },
        ),
      );

    await api.conversations.create();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/conversations"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-test-token" }),
      }),
    );
  });

  it("includes browser credentials on protected read requests", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            success: true,
            data: {},
            error: null,
            meta: null,
          }),
          { status: 200 },
        ),
      ),
    );

    await api.conversations.active();
    await api.conversations.list();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/api/conversations/active"),
      expect.objectContaining({ credentials: "include" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/api/conversations"),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("does not put session tokens in the login request body", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({ success: true, data: {}, error: null, meta: null }),
          { status: 200 },
        ),
      );

    await api.auth.login("student", "Student-pass-123");
    const [, options] = fetchMock.mock.calls[0];
    expect(String(options?.body)).not.toContain("access_token");
    expect(String(options?.body)).not.toContain("refresh_token");
  });

  it("sends invite registration fields using the browser session", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({ success: true, data: {}, error: null, meta: null }),
          { status: 201 },
        ),
      );

    await api.auth.register({
      username: "student",
      password: "Student-pass-123",
      inviteCode: "invite-code",
      displayName: "Student One",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/auth/register"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-test-token" }),
        body: JSON.stringify({
          username: "student",
          password: "Student-pass-123",
          invite_code: "invite-code",
          display_name: "Student One",
        }),
      }),
    );
  });

  it("omits an empty optional display name from registration", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({ success: true, data: {}, error: null, meta: null }),
          { status: 201 },
        ),
      );

    await api.auth.register({
      username: "student",
      password: "Student-pass-123",
      inviteCode: "invite-code",
    });

    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.display_name).toBeUndefined();
  });

  it("supports refresh, logout, and current-user requests", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            success: true,
            data: {},
            error: null,
            meta: null,
          }),
          { status: 200 },
        ),
      ),
    );

    await api.auth.refresh();
    await api.auth.logout();
    await api.auth.me();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/api/auth/refresh"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf-test-token" }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/api/auth/logout"),
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("/api/auth/me"),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("turns an error envelope into a useful client error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          success: false,
          data: null,
          error: { code: "AUTH_REQUIRED", message: "请先登录" },
          meta: null,
        }),
        { status: 403 },
      ),
    );

    await expect(api.auth.me()).rejects.toThrow("请先登录");
  });

  it("refreshes once and retries a protected request after access expiry", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            success: false,
            data: null,
            error: { code: "AUTH_REQUIRED", message: "会话已过期" },
            meta: null,
          }),
          { status: 401 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ success: true, data: {}, error: null, meta: null }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            success: true,
            data: {
              id: 7,
              title: "恢复后的会话",
              summary: null,
              message_count: 0,
              last_message_at: null,
              created_at: "2026-08-04T00:00:00Z",
              updated_at: "2026-08-04T00:00:00Z",
            },
            error: null,
            meta: null,
          }),
          { status: 200 },
        ),
      );

    const conversation = await api.conversations.active();

    expect(conversation.title).toBe("恢复后的会话");
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      expect.stringContaining("/api/conversations/active"),
      expect.stringContaining("/api/auth/refresh"),
      expect.stringContaining("/api/conversations/active"),
    ]);
  });
});
