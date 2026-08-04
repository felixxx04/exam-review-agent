import { test, expect } from "@playwright/test";

const ok = (data: unknown) => ({
  success: true,
  data,
  error: null,
  meta: null,
});

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};

    if (path === "/api/auth/me") {
      data = {
        id: 1,
        username: "smoke_user",
        display_name: "Smoke User",
        role: "user",
        is_disabled: false,
        created_at: "2026-08-04T00:00:00Z",
      };
    } else if (
      path === "/api/auth/login" ||
      path === "/api/auth/register" ||
      path === "/api/auth/refresh"
    ) {
      data = {
        user: {
          id: 1,
          username: "smoke_user",
          display_name: "Smoke User",
          role: "user",
          is_disabled: false,
          created_at: "2026-08-04T00:00:00Z",
        },
        access_expires_at: "2026-08-04T00:15:00Z",
        refresh_expires_at: "2026-09-03T00:00:00Z",
      };
    } else if (path === "/api/conversations/active") {
      data = {
        id: 1,
        title: "新的复习会话",
        summary: null,
        message_count: 0,
        last_message_at: null,
        created_at: "2026-08-03T00:00:00Z",
        updated_at: "2026-08-03T00:00:00Z",
      };
    } else if (path === "/api/conversations/1/messages") {
      data = { conversation_id: 1, messages: [] };
    } else if (path === "/api/conversations") {
      data = { conversations: [], total: 0 };
    } else if (path === "/api/materials") {
      data = { materials: [], total: 0 };
    } else if (path === "/api/review/weak-points") {
      data = { weak_concepts: [], total_questions: 0, accuracy: 0 };
    } else if (path === "/api/review/mistakes") {
      data = {
        mistakes: [],
        total: 0,
        summary: {
          total_count: 0,
          pending_count: 0,
          mastered_count: 0,
          corrected_count: 0,
          needs_requiz_count: 0,
        },
      };
    } else {
      await route.fulfill({
        status: 404,
        json: {
          success: false,
          data: null,
          error: { code: "UNMOCKED_API", message: path },
          meta: null,
        },
      });
      return;
    }

    await route.fulfill({ json: ok(data) });
  });
});

test("page loads with header and mode tabs", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toHaveText("AI 学习工作台");
  await expect(page.getByRole("tab", { name: /问答/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /测验/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /复习/ })).toBeVisible();
});

test("switching to quiz mode shows quiz empty state", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /测验/ }).click();
  await expect(page.getByText(/开始一次测验/)).toBeVisible();
});

test("switching to review mode shows dashboard empty state", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /复习/ }).click();
  await expect(page.getByText("完成测验后会自动生成薄弱点。")).toBeVisible();
});

test("materials upload button exists", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "上传资料" })).toBeVisible();
});

test("user can log in and enter the learning workspace", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("用户名").fill("smoke_user");
  await page.getByLabel("密码").fill("Student-pass-123");
  await page.getByRole("button", { name: "登录" }).click();

  await expect(page).toHaveURL("/");
  await expect(page.getByRole("tab", { name: /问答/ })).toBeVisible();
});

test("user can register with an invite and enter the workspace", async ({
  page,
}) => {
  await page.goto("/register");
  await page.getByLabel("用户名").fill("smoke_user");
  await page.getByLabel("显示名称").fill("Smoke User");
  await page.getByLabel("邀请码").fill("smoke-invite-code");
  await page.getByLabel("密码", { exact: true }).fill("Student-pass-123");
  await page.getByLabel("确认密码").fill("Student-pass-123");
  await page.getByRole("button", { name: "创建账号" }).click();

  await expect(page).toHaveURL("/");
  await expect(page.getByRole("tab", { name: /问答/ })).toBeVisible();
});
