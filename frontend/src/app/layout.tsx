import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Exam Review Agent",
  description: "AI-powered exam review with RAG Q&A, auto-quiz, and mistake tracking",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
