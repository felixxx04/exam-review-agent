# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20260608-001] best_practice

**Logged**: 2026-06-08T12:23:00+08:00
**Priority**: high
**Status**: pending
**Area**: config

### Summary
Always run skill-vetter audit before installing any skill from ClawdHub, GitHub, or other sources.

### Details
User explicitly requested: whenever installing a new skill, call the skill-vetter audit skill first to check for red flags, permission scope, and suspicious patterns.

### Suggested Action
Before every `openclaw skills install <name>` call, first read and follow `D:\ai-agent\skills\skill-vetter\SKILL.md` vetting protocol.

### Metadata
- Source: user_feedback
- Tags: security, skill-install, workflow

---
