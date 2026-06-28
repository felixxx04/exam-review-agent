import { test, expect } from "@playwright/test";

test("page loads with header and mode tabs", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toHaveText("Exam Review");
  await expect(page.getByRole("tab", { name: /问答/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /测验/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /复习/ })).toBeVisible();
});

test("switching to quiz mode shows quiz empty state", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /测验/ }).click();
  await expect(page.getByText(/开始一次测验/)).toBeVisible();
});

test("switching to review mode shows dashboard empty state", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /复习/ }).click();
  await expect(page.getByText(/暂无薄弱知识点/)).toBeVisible();
});

test("materials upload button exists", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/上传资料/)).toBeVisible();
});
