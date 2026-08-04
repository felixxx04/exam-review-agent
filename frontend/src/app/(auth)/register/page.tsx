"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BadgeCheck,
  Loader2,
  LockKeyhole,
  Ticket,
  UserRound,
} from "lucide-react";
import { AuthShell } from "@/components/auth/AuthShell";
import { api } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirmation) {
      setError("两次输入的密码不一致");
      return;
    }
    setSubmitting(true);
    try {
      await api.auth.register({ username, displayName, inviteCode, password });
      router.replace("/");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "注册失败，请稍后重试",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="创建学习账号"
      subtitle="使用收到的邀请码加入。"
      alternateText="已经有账号？"
      alternateLabel="返回登录"
      alternateHref="/login"
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <div className="auth-field-row">
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
            <span>显示名称</span>
            <span className="auth-input-shell">
              <BadgeCheck size={18} aria-hidden="true" />
              <input
                name="displayName"
                autoComplete="name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                required
              />
            </span>
          </label>
        </div>
        <label className="auth-field">
          <span>邀请码</span>
          <span className="auth-input-shell">
            <Ticket size={18} aria-hidden="true" />
            <input
              name="inviteCode"
              autoComplete="off"
              value={inviteCode}
              onChange={(event) => setInviteCode(event.target.value)}
              required
            />
          </span>
        </label>
        <div className="auth-field-row">
          <label className="auth-field">
            <span>密码</span>
            <span className="auth-input-shell">
              <LockKeyhole size={18} aria-hidden="true" />
              <input
                name="password"
                type="password"
                autoComplete="new-password"
                minLength={10}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </span>
          </label>
          <label className="auth-field">
            <span>确认密码</span>
            <span className="auth-input-shell">
              <LockKeyhole size={18} aria-hidden="true" />
              <input
                name="confirmation"
                type="password"
                autoComplete="new-password"
                minLength={10}
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                required
              />
            </span>
          </label>
        </div>
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
          <span>创建账号</span>
        </button>
      </form>
    </AuthShell>
  );
}
