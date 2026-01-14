# Story 27: Unified Response Interface (Single Message UX)

**Epic:** Epic 6 - MVP Polish (UX Improvement)
**Parent:** .cursor/tz/org_prd.md
**Branch:** `feature/ux-unified-response`
**Prerequisites:** None (Can be done anytime)

## Context
Current behavior splits AI text responses and "Button Lists" into mutually exclusive modes, or risks sending multiple messages which is bad UX.
**Goal:** Always provide the rich Contextual Answer from LLM *combined* with interactive Action Buttons (Edit/Delete) in a **single message**.

## Technical Concept
Instead of choosing between `Text` OR `List`, the `AIService` should return a hybrid object. The Handler will construct a single Telegram message where:
1.  **Text Body:** The smart LLM response (HTML formatted).
2.  **Inline Keyboard:** A generated grid of buttons for the contacts mentioned in the text.

### Challenge
Telegram buttons have limits (callback data length). We need to map buttons to contacts efficiently.

## Technical Tasks

### 1. AIService Refactoring
- [ ] Create `CompositeResponse` class:
    ```python
    class CompositeResponse(BaseModel):
        text: str
        related_contacts: List[SearchResult] # Contacts mentioned/found
    ```
- [ ] Update `run_router_agent` to return `CompositeResponse`.
    -   If tool `search_contacts` is used, store results in `related_contacts`.
    -   Pass `related_contacts` through to the final return along with the LLM's final text.

### 2. Handler Update (`app/handlers/text.py`)
- [ ] Update `handle_agent_response` to accept `CompositeResponse`.
- [ ] Logic:
    -   `text = response.text`
    -   `keyboard = Builder()`
    -   Iterate `response.related_contacts`:
        -   Add button `[ ✏️ Name ]` (Edit) or `[ 🗑 Name ]` (Delete) or just `[ ⚙️ Name ]` (Menu).
        -   Callback: `contact_menu_{id}`.
- [ ] Send **ONE** message with `text` and `markup`.

### 3. Contact Menu Handler
- [ ] Implement `contact_menu_{id}` callback handler.
- [ ] When clicked, edit message (or send ephemeral) with actions for that specific contact:
    -   "Delete"
    -   "Edit"
    -   "Move to Org"

## Acceptance Criteria
- [ ] User asks "Who is Sergey?".
- [ ] Bot replies in ONE message:
    > "Sergey is a Python dev from Tinder..."
    > [ ⚙️ Sergey ] [ ⚙️ Sasha ]
- [ ] Clicking `[ ⚙️ Sergey ]` opens actions for Sergey.
- [ ] No double messages.

## Definition of Done
- [ ] Refactored AIService to return Composite data.
- [ ] Refactored Handler to render hybrid message.
