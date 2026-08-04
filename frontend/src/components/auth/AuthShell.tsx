import Link from "next/link";
import { BookOpenCheck } from "lucide-react";

interface AuthShellProps {
  title: string;
  subtitle: string;
  alternateText: string;
  alternateLabel: string;
  alternateHref: string;
  children: React.ReactNode;
}

export function AuthShell({
  title,
  subtitle,
  alternateText,
  alternateLabel,
  alternateHref,
  children,
}: AuthShellProps) {
  return (
    <main className="auth-page">
      <section className="auth-brand" aria-labelledby="auth-brand-title">
        <div className="auth-brand-mark" aria-hidden="true">
          <BookOpenCheck size={28} strokeWidth={1.8} />
        </div>
        <div>
          <p className="auth-brand-kicker">EXAM REVIEW AGENT</p>
          <h1 id="auth-brand-title">AI 学习工作台</h1>
          <p className="auth-brand-note">继续今天的学习节奏。</p>
        </div>
      </section>

      <section className="auth-form-panel" aria-labelledby="auth-form-title">
        <header className="auth-form-header">
          <h2 id="auth-form-title">{title}</h2>
          <p>{subtitle}</p>
        </header>
        {children}
        <p className="auth-alternate">
          {alternateText}
          <Link href={alternateHref}>{alternateLabel}</Link>
        </p>
      </section>
    </main>
  );
}
