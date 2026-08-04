import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginPage from "@/app/(auth)/login/page";
import RegisterPage from "@/app/(auth)/register/page";
import { api } from "@/lib/api";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    auth: {
      login: vi.fn(),
      register: vi.fn(),
    },
  },
}));

describe("authentication pages", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.mocked(api.auth.login).mockReset();
    vi.mocked(api.auth.register).mockReset();
  });

  it("submits login and returns to the learning workspace", async () => {
    vi.mocked(api.auth.login).mockResolvedValue({} as never);
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText("用户名"), "student");
    await user.type(screen.getByLabelText("密码"), "Student-pass-123");
    await user.click(screen.getByRole("button", { name: "登录" }));

    expect(api.auth.login).toHaveBeenCalledWith("student", "Student-pass-123");
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("shows a recoverable login error", async () => {
    vi.mocked(api.auth.login).mockRejectedValue(new Error("账号或密码不正确"));
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText("用户名"), "student");
    await user.type(screen.getByLabelText("密码"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "账号或密码不正确",
    );
  });

  it("submits an invite registration", async () => {
    vi.mocked(api.auth.register).mockResolvedValue({} as never);
    const user = userEvent.setup();
    render(<RegisterPage />);

    await user.type(screen.getByLabelText("用户名"), "student");
    await user.type(screen.getByLabelText("显示名称"), "期末复习者");
    await user.type(screen.getByLabelText("邀请码"), "invite-code");
    await user.type(screen.getByLabelText("密码"), "Student-pass-123");
    await user.type(screen.getByLabelText("确认密码"), "Student-pass-123");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(api.auth.register).toHaveBeenCalledWith({
      username: "student",
      displayName: "期末复习者",
      inviteCode: "invite-code",
      password: "Student-pass-123",
    });
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("blocks registration when password confirmation differs", async () => {
    const user = userEvent.setup();
    render(<RegisterPage />);

    await user.type(screen.getByLabelText("用户名"), "student");
    await user.type(screen.getByLabelText("显示名称"), "期末复习者");
    await user.type(screen.getByLabelText("邀请码"), "invite-code");
    await user.type(screen.getByLabelText("密码"), "Student-pass-123");
    await user.type(screen.getByLabelText("确认密码"), "Different-pass-123");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "两次输入的密码不一致",
    );
    expect(api.auth.register).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows a recoverable registration error", async () => {
    vi.mocked(api.auth.register).mockRejectedValue(new Error("邀请码不可用"));
    const user = userEvent.setup();
    render(<RegisterPage />);

    await user.type(screen.getByLabelText("用户名"), "student");
    await user.type(screen.getByLabelText("显示名称"), "期末复习者");
    await user.type(screen.getByLabelText("邀请码"), "invite-code");
    await user.type(screen.getByLabelText("密码"), "Student-pass-123");
    await user.type(screen.getByLabelText("确认密码"), "Student-pass-123");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("邀请码不可用");
    expect(replace).not.toHaveBeenCalled();
  });
});
