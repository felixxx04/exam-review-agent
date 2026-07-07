"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { MATERIAL_FILE_ACCEPT } from "@/lib/config";
import { conversationMessageToMessages } from "@/lib/conversationMessages";
import { useChatStream } from "@/hooks/useChatStream";
import { useMaterials } from "@/hooks/useMaterials";
import { useChatStore } from "@/stores/chatStore";
import { AppSidebar } from "@/components/AppSidebar";
import { Header } from "@/components/Header";
import { MessageList } from "@/components/MessageList";
import { ChatInput } from "@/components/ChatInput";
import { QuizCard } from "@/components/QuizCard";
import { DashboardCard } from "@/components/DashboardCard";
import type { Material } from "@/types";
import {
  BarChart3,
  FileText,
  Loader2,
  MessageCircle,
  Upload,
} from "lucide-react";

export default function Home() {
  const {
    messages,
    mode,
    isStreaming,
    materialScope,
    setConversationId,
    setMaterialScope,
    setMessages,
    setMode,
  } = useChatStore();
  const {
    materials,
    loading: materialsLoading,
    uploadMaterial,
    deleteMaterial,
    refetch,
  } = useMaterials();
  const { sendMessage } = useChatStream({
    onConversationChange: refreshConversations,
  });
  const [uploading, setUploading] = useState(false);
  const [conversationsVersion, setConversationsVersion] = useState(0);
  const quickUploadRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadConversation() {
      const conversation = await api.conversations.active();
      const history = await api.conversations.messages(conversation.id);
      if (cancelled) return;

      setConversationId(conversation.id);
      setMessages(history.messages.flatMap(conversationMessageToMessages));
      const lastScope = [...history.messages]
        .reverse()
        .find(
          (message) =>
            message.material_scope && message.material_scope.length > 0,
        )?.material_scope;
      setMaterialScope(lastScope ?? []);
    }

    loadConversation().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [setConversationId, setMaterialScope, setMessages]);

  useEffect(() => {
    const hasPending = materials.some(
      (material) =>
        material.processing_status === "pending" ||
        material.processing_status === "processing",
    );
    if (!hasPending) return;

    const id = window.setInterval(refetch, 3000);
    return () => window.clearInterval(id);
  }, [materials, refetch]);

  async function handleUpload(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await uploadMaterial(file);
      }
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteMaterial(id: number) {
    const material = materials.find((item) => item.id === id);
    await deleteMaterial(id);
    if (!material) return;

    setMaterialScope(
      materialScope.filter(
        (filename) => filename !== material.original_filename,
      ),
    );
  }

  function refreshConversations() {
    setConversationsVersion((version) => version + 1);
  }

  const readyMaterials = materials.filter(
    (material) => material.processing_status === "ready",
  );
  const activeMaterial =
    materials.find((material) =>
      materialScope.includes(material.original_filename),
    ) ??
    readyMaterials[0] ??
    materials[0];

  return (
    <div className="app-shell">
      <AppSidebar
        conversationsVersion={conversationsVersion}
        materials={materials}
        materialsLoading={materialsLoading}
        uploading={uploading}
        onUpload={handleUpload}
        onDeleteMaterial={handleDeleteMaterial}
        onConversationChange={refreshConversations}
      />

      <main className="app-main">
        <Header onConversationChange={refreshConversations} />
        <div className="app-content">
          {mode === "ask" && (
            <section className="ask-workspace" aria-label="问答工作区">
              <div className="ask-scroll-area">
                {messages.length === 0 ? (
                  <QuickActions
                    activeMaterial={activeMaterial}
                    materials={materials}
                    uploading={uploading}
                    disabled={isStreaming}
                    onUploadClick={() => quickUploadRef.current?.click()}
                    onQuestionClick={(question) => sendMessage(question)}
                    onReviewClick={() => setMode("review")}
                  />
                ) : (
                  <MessageList />
                )}
              </div>
              <input
                ref={quickUploadRef}
                type="file"
                multiple
                accept={MATERIAL_FILE_ACCEPT}
                className="hidden"
                onChange={async (event) => {
                  const input = event.currentTarget;
                  const files = input.files;
                  await handleUpload(files);
                  input.value = "";
                }}
                aria-label="上传复习资料"
              />
              <ChatInput onConversationChange={refreshConversations} />
            </section>
          )}
          {mode === "quiz" && <QuizCard />}
          {mode === "review" && <DashboardCard />}
        </div>
      </main>
    </div>
  );
}

interface QuickActionsProps {
  activeMaterial: Material | undefined;
  materials: Material[];
  uploading: boolean;
  disabled: boolean;
  onUploadClick: () => void;
  onQuestionClick: (question: string) => void;
  onReviewClick: () => void;
}

function QuickActions({
  activeMaterial,
  materials,
  uploading,
  disabled,
  onUploadClick,
  onQuestionClick,
  onReviewClick,
}: QuickActionsProps) {
  const materialName = activeMaterial?.original_filename ?? "MQ.docx";
  const questions = [
    `请总结 ${materialName} 的考试重点`,
    `根据 ${materialName} 推荐 3 个最值得练习的问题`,
    `梳理 ${materialName} 中容易混淆的概念`,
  ];

  return (
    <div className="quick-actions">
      <div className="quick-actions-heading">
        <p className="eyebrow">AI Study Workspace</p>
        <h2>把复习资料整理成可追问、可测验、可沉淀的学习工作台</h2>
        <p>
          上传课程资料后，从问答、测验到错题复盘都围绕同一份知识上下文展开。先选择左侧文档，或直接从下方快捷操作开始。
        </p>
      </div>

      <div className="quick-action-grid">
        <article className="quick-card">
          <div className="quick-card-icon">
            {uploading ? (
              <Loader2 size={22} className="upload-spinner animate-spin" />
            ) : (
              <Upload size={22} />
            )}
          </div>
          <div>
            <h3>上传资料</h3>
            <p>支持 PDF、DOCX、PPTX。上传完成后可在左侧文档库选择范围。</p>
          </div>
          <div className="document-strip">
            {materials.length === 0 ? (
              <span className="document-chip muted">
                <FileText size={14} />
                MQ.docx
              </span>
            ) : (
              materials.slice(0, 3).map((material) => (
                <span className="document-chip" key={material.id}>
                  <FileText size={14} />
                  {material.original_filename}
                </span>
              ))
            )}
          </div>
          <button
            type="button"
            className="quick-card-button"
            onClick={onUploadClick}
            disabled={uploading}
          >
            {uploading ? "上传中" : "选择文件"}
          </button>
        </article>

        <article className="quick-card quick-card-wide">
          <div className="quick-card-icon">
            <MessageCircle size={22} />
          </div>
          <div>
            <h3>推荐提问</h3>
            <p>基于当前资料快速开始问答，点击任意问题会直接发送。</p>
          </div>
          <div className="recommended-questions">
            {questions.map((question) => (
              <button
                type="button"
                key={question}
                onClick={() => onQuestionClick(question)}
                disabled={disabled}
              >
                {question}
              </button>
            ))}
          </div>
        </article>

        <article className="quick-card">
          <div className="quick-card-icon">
            <BarChart3 size={22} />
          </div>
          <div>
            <h3>薄弱知识点复习</h3>
            <p>查看测验后沉淀的薄弱概念，并针对低正确率内容重新练习。</p>
          </div>
          <button
            type="button"
            className="quick-card-button secondary"
            onClick={onReviewClick}
          >
            查看复习面板
          </button>
        </article>
      </div>
    </div>
  );
}
