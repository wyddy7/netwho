# Story 07: Agentic Onboarding & News-Jacking (Personal CRM 2.0)

## 🎯 Goal
Transform the bot from a passive tool into an active partner via seamless onboarding (no surveys) and intelligent reaction to external content (links).

## 📦 Deliverables

### 1. Agentic Onboarding (The "Magic Moment" Flow)
*Approach: "One-Shot Learning" instead of a boring wizard.*

- [ ] **Step 1 (Persona)**:
    - Bot asks: *"Who are you and who are you looking for?"* (with prompt buttons: `👨‍💻 Startup Founder`, `💰 Investor`, `🎤 Networker`).
    - **Analysis**: LLM extracts `bio` and `interests` immediately, confirming understanding: *"Got it, you're a Product Manager. I'll keep an eye out for investors and techies."*
- [ ] **Step 2 (First Contact)**:
    - Bot requests: *"Recall one important person you haven't messaged in a while."*
    - **Magic Moment**: Immediately after saving, trigger **Recall**, suggesting a valid reason to message them *right now*.
- [ ] **Step 3 (Progressive Profiling)**:
    - **DO NOT ASK** for frequency settings initially. Default to "Weekly". Ask later once the user sees value.

### 2. News-Jacking (Content Reaction)
- [ ] **Link Handler**:
    - Intercept messages containing URLs.
    - Use **Jina Reader** (`https://r.jina.ai/URL`) to fetch clean article text (no API keys needed).
    - **Matchmaking**: Search DB for contacts who might find this article interesting (Vector Search).
    - **Output**: *"Oh, an article about AI Agents. Send this to Nikita (Coder) and Kamil (CTO), they'd love it."*

### 3. Smart Recall Algorithm
- [ ] **Priority Logic**:
    - Replace pure random with weighted selection.
    - Logic: Prioritize contacts with `last_interaction` (or `created_at`) that are oldest.
    - Select top candidate(s) from the "neglected" pool.

## 🛠 Technical Implementation

### A. FSM & States (`app/states.py`)
- Simplified States: `OnboardingStates.waiting_for_bio` -> `OnboardingStates.waiting_for_first_contact`.
- Use `MemoryStorage` (Aiogram) is sufficient for MVP.

### B. News Service (`app/services/news_service.py`)
- Implement `fetch_article_content(url: str)` using `aiohttp` + Jina Reader.
- Integrate with `search_service` to find relevant contacts based on article summary.

### C. Refactoring
- Update `recall_service.py`: 
    - Add sorting by date (`created_at` or `last_interaction` ASC NULLS FIRST).
    - Pick from the top "neglected" contacts (e.g., random from top 20).

## 📝 Success Criteria
1. New user completes onboarding in **2 steps** (Bio -> Contact) and immediately gets a **WOW-effect** (ready-to-send message).
2. Sending a TechCrunch link triggers a suggestion to forward it to a specific relevant contact.
3. Bot no longer asks unnecessary scheduling questions at start.
