"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, LockKeyhole, UserRound } from "lucide-react";
import { AuthShell } from "@/components/auth/AuthShell";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await api.auth.login(username, password);
      router.replace("/");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "登录失败，请稍后重试",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="欢迎回来"
      subtitle="登录后继续你的复习进度。"
      alternateText="还没有账号？"
      alternateLabel="使用邀请码注册"
      alternateHref="/register"
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <label className="auth-field">
          <span>用户名</span>
          <span className="auth-input-shell">
            <UserRound size={18} aria-hidden="true" />
            <input
              name="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </span>
        </label>
        <label className="auth-field">
          <span>密码</span>
          <span className="auth-input-shell">
            <LockKeyhole size={18} aria-hidden="true" />
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </span>
        </label>
        {error ? (
          <p className="auth-error" role="alert">
            {error}
          </p>
        ) : null}
        <button className="auth-submit" type="submit" disabled={submitting}>
          {submitting ? (
            <Loader2 className="animate-spin" size={18} aria-hidden="true" />
          ) : (
            <ArrowRight size={18} aria-hidden="true" />
          )}
          <span>登录</span>
        </button>
      </form>
    </AuthShell>
  );
}
