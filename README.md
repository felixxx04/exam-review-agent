# 期末复习 Agent

面向大学生期末复习场景的 AI 学习助手。用户可以上传课件或讲义，基于资料进行问答、生成练习题、查看薄弱点，并在 `Ask / Quiz / Review` 三种模式之间切换完成复习闭环。

## 项目概述

项目围绕 `AI Agent + RAG + 全栈工程` 构建，目标是将资料管理、问答、出题、错题跟踪和前后端交互整合为统一的学习系统，支持学生围绕课程资料完成高频复习任务。

## 核心功能

- 资料上传：支持上传 `PDF / DOCX / PPTX`
- 智能问答：围绕上传资料进行问答，后端支持流式返回
- 题目生成：按知识点、难度、数量生成练习题
- 错题分析：记录答题结果并输出薄弱点视图
- 学习模式切换：提供 `Ask / Quiz / Review` 三种复习模式
- 基础安全处理：对聊天输入做简单的提示注入检测

## 技术方案

### 前端

- Next.js 15 + React 19
- TypeScript
- Zustand
- Tailwind CSS
- Playwright + Vitest

### 后端

- FastAPI
- LangGraph / LangChain
- SQLAlchemy + Alembic
- ChromaDB
- Redis / ARQ

### 大模型与检索

- 支持通过配置接入 DeepSeek、GLM、MiniMax、火山引擎等模型
- 基于资料解析与检索结果驱动问答、出题和复习流程

## 系统结构

```text
frontend (Next.js)
  ├─ Ask 模式：聊天问答
  ├─ Quiz 模式：练习题生成与提交
  └─ Review 模式：薄弱点和复习建议

backend (FastAPI)
  ├─ /api/chat        流式问答
  ├─ /api/materials   资料上传/查询/删除
  ├─ /api/quiz        题目生成/提交评分
  └─ /api/review      薄弱点与学习计划

agent layer
  ├─ RAG Agent
  ├─ Quiz Agent
  └─ Tracker Agent
```

## 项目实现

- 实现问答、出题、复习三条核心流程及其前后端交互
- 完成资料栏、消息流、题卡、复习面板等主要界面组件
- 提供 `chat / materials / quiz / review / health` 等核心接口
- 接入多模型配置，支持基于环境变量切换默认 LLM Provider
- 编写后端单元测试、接口测试，并配置前端单测与 E2E 测试脚本

## 当前仓库已实现内容

- 前端具备可交互的三模式界面
- 后端已提供 `chat / materials / quiz / review / health` 接口
- 支持本地 SQLite 开发环境
- 已编写后端测试用例，覆盖 Agent、服务层和 API
- 已配置前端单测与 E2E 测试脚本

## 目录结构

```text
.
├─ frontend/   # Next.js 前端
├─ backend/    # FastAPI 后端
├─ docs/       # 设计文档与计划文档
├─ memory/     # 项目过程产物
└─ skills/     # 项目中使用的技能与工作流沉淀
```

## 本地运行

### 1. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

需要在 `.env` 中至少配置：

- 一个可用的模型 API Key
- `DEFAULT_LLM_PROVIDER`
- `JWT_SECRET`

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认访问 `http://localhost:8000`，如有需要可通过 `NEXT_PUBLIC_API_URL` 覆盖。

## 测试

后端测试：

```bash
cd backend
pytest
```

前端单测：

```bash
cd frontend
npm test
```

前端 E2E：

```bash
cd frontend
npm run test:e2e
```

## 后续优化方向

- 完善真正的资料切片、向量检索和引用链路
- 增加更完整的学习计划与复习调度能力
- 补充更多端到端测试和真实复习数据验证
