# Brave integration: capture and outbound message transport

Status: planned
Integration base: feature/worker-mvp
Implementation branch: feature/brave-chat-bridge

## Goal
Build a Brave/Chromium Manifest V3 extension that detects a newly completed ChatGPT assistant answer using the Stop button lifecycle, extracts the final message and supports receiving and submitting a new message through a controlled browser bridge.

## Scope
- Content script, service worker and side panel.
- State machine for running, completion, cancellation, reload, SPA navigation, tab/conversation identity and deduplication.
- Capture text from the final assistant message, not prior history; preserve code blocks and line breaks.
- Receive outbound text from a localhost adapter or mock, stage it, and submit through the ChatGPT composer only when explicitly authorized by the outbound policy.
- Mock backend and test harness. No Ollama, SSH or live service deployment.
- Explicitly distinguish API message delivery, composer insertion and actual submit acknowledgement.

## Protected decisions
- Stop button is the primary completion signal, with stabilization and cancellation checks.
- Automatic outbound submission is reserved for the result of a previously approved SSH batch, and must be tied to the original conversation and tab.
- Arbitrary inbound text may be staged for manual submission but must never auto-send.
- Browser extension does not possess SSH credentials.
- Least-privilege MV3 permissions and authenticated loopback transport.
- Existing backend contracts in docs/protocol.md are not silently redefined.

## Acceptance tests
- One completed assistant message -> one capture, preserving code formatting.
- Streaming and intermediate DOM changes -> no premature capture.
- Manual stop -> no false success.
- Reload, repeated DOM mutations and reconnect -> no duplicates.
- Conversation/tab changes -> no cross-chat auto-send.
- Outbound staging -> composer populated but not submitted without policy approval.
- Approved-result fixture -> exactly one submit in correct conversation; delivery state persisted or reconciled.
- API disconnect, timeout, 401, unexpected UI selectors -> visible failure and safe recovery.
- Browser smoke test required before declaring runtime support.

## Handoff
Implement independently on feature/brave-chat-bridge, maintain this document while unfinished, report tests and commits. Do not merge without user approval.
