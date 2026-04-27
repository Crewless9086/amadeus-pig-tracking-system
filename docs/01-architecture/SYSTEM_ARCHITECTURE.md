# System Architecture

> Migrated from legacy system architecture.

---

1. PURPOSE
This system is designed to manage:

Customer conversations
Order creation and tracking
Stock-aware decision making
Human escalation when needed

The system must operate as a single intelligent workflow, even though it is built across multiple platforms.

2. CORE COMPONENTS
2.1 Chatwoot (Communication Layer)
Handles:

Incoming messages (WhatsApp, Messenger, Telegram, Instagram, Web Chatbot.)
Conversation tracking
User identity
Message sending

Chatwoot is the entry and exit point of the system. This is the single used Inbox.

2.2 n8n (Orchestration Engine)
Handles:

Workflow execution
Decision routing
AI agent calls
Data transformation
Triggering backend actions

n8n is the brain that connects everything.

2.3 AI Agents (Decision Layer)
Includes:

Sales Agent (SAM)
Escalation Classifier
Clarification Handler

Responsible for:

Understanding user intent
Generating responses
Deciding next actions

AI does NOT store data — it only interprets and responds.

2.4 Backend (Flask API)
Handles:

Order creation
Order updates
Stock validation
Business logic enforcement

Backend is the source of truth for all transactional data.

2.5 Google Sheets (Data Layer)
Stores:

Orders
Order lines
Stock availability
Escalation logs

Sheets are the current database, but logic must not live here.

3. SYSTEM FLOW (HIGH LEVEL)


User sends message → Chatwoot

Chatwoot triggers n8n webhook

n8n normalizes message

AI evaluates intent

System decides:
→ Auto reply
→ Clarification
→ Order processing
→ Human escalation

If needed:
→ Backend is called for order actions
→ Sheets updated

Final reply is sent via Chatwoot


4. RESPONSIBILITY RULES

Component
Responsibility

Chatwoot
Messaging only

n8n
Logic + orchestration

AI Agents
Interpretation + response

Backend
Data truth + business rules

Sheets
Data storage


5. CRITICAL PRINCIPLES
5.1 Single Source of Truth

Orders → Backend
Stock → Sheets (for now)
Conversations → Chatwoot


5.2 No Logic Duplication
Logic must NOT be:

split between n8n and backend
recreated inside AI prompts
embedded in Google Sheets formulas


5.3 Controlled Data Flow
Each step must:

receive structured input
produce structured output

No hidden transformations.

5.4 Deterministic Workflow
Same input = same output
(No random behavior)

6. FUTURE STATE
This system will evolve into:

Fully API-driven backend
Reduced reliance on Google Sheets
Stronger AI decision agents
Modular workflows (plug-and-play)


7. WHAT THIS DOCUMENT DOES
This document defines:

The system structure
The role of each component
The boundaries between systems

It does NOT define:

Node-level logic
Field mappings
Workflow decisions

Those are defined in other documents.
