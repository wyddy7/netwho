# NetWho

NetWho is an AI-powered personal network manager bot for Telegram. It helps you keep track of your contacts, suggests when to reconnect, and provides AI-driven insights.

## Features

- **Smart Contact Management**: Save contacts via voice or text. AI extracts names, roles, and details.
- **Recall System**: Automatically reminds you to reconnect with people you haven't spoken to in a while.
- **News Jacking**: Send a link to an article, and NetWho will suggest which of your contacts might be interested.
- **Voice Interface**: Full support for voice messages.
- **Pro Mode**: Extended features and limits.

## Commands

### User Commands

- `/start` - Start or restart the bot (Onboarding).
- `/settings` - Open settings menu (Timezone, Focus, etc.).
- `/profile` - View your profile and stats.
- `/recall` - Manually trigger a recall suggestion.
- `/delete_me` - Delete all your data (Soft reset: subscription status is preserved).
- `/help` - Show help message.

### Admin Commands

*Available only to the configured ADMIN_ID.*

- `/admin` - Show list of admin commands.
- `/give_pro <user_id> <days>` - Grant Pro subscription to a user for N days.
- `/revoke_pro <user_id>` - Revoke Pro subscription (expire immediately).
- `/check_user <user_id>` - View user details (Bio, Subscription status).

## Setup & Deployment

1. **Clone the repository**
2. **Configure Environment**:
   Copy `.env.example` to `.env` and fill in:
   - `BOT_TOKEN`: Telegram Bot Token
   - `SUPABASE_URL`: Supabase Project URL
   - `SUPABASE_KEY`: Supabase Service Role Key
   - `OPENROUTER_API_KEY`: API Key for LLM
   - `ADMIN_ID`: Telegram User ID of the administrator
3. **Run with Docker**:
   ```bash
   docker-compose up --build -d
   ```

## Development

- Built with `aiogram 3.x` (Python).
- Database: Supabase (PostgreSQL).
- AI: OpenAI / OpenRouter.

## Subscription Logic

- **New Users**: Get a 3-day trial automatically upon first registration.
- **Returning Users**: If a user deletes their account (`/delete_me`) and returns, they **do not** get a new trial. Their previous subscription status is preserved.
- **Legacy Users**: No automatic trials for old users. Admins can grant trials manually using `/grant_pro`.

