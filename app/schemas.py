from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

# --- User Schemas ---
class UserSettings(BaseModel):
    # True = спрашивать подтверждение (Безопасный режим)
    # False = Rage Mode (сразу делать)
    confirm_add: bool = True 
    confirm_delete: bool = True

class UserBase(BaseModel):
    username: str | None = None
    full_name: str
    is_premium: bool = False
    terms_accepted: bool = False
    settings: UserSettings = Field(default_factory=UserSettings)

class UserCreate(UserBase):
    id: int  # Telegram ID

class UserInDB(UserCreate):
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- Contact Schemas ---
class ContactMeta(BaseModel):
    role: str | None = None
    company: str | None = None
    interests: list[str] = Field(default_factory=list)
    hobbies: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    social: list[str] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)

class ContactExtracted(BaseModel):
    name: str
    summary: str
    meta: ContactMeta

class ContactCreate(BaseModel):
    user_id: int
    name: str
    summary: str | None = None
    raw_text: str | None = None
    meta: dict = Field(default_factory=dict)
    embedding: list[float] | None = None

class ContactDraft(ContactCreate):
    """Промежуточный объект для подтверждения добавления"""
    pass

class ContactDeleteAsk(BaseModel):
    """Объект запроса подтверждения удаления"""
    contact_id: str
    name: str
    summary: str | None

class ActionConfirmed(BaseModel):
    """Сигнал о подтверждении действия из текста"""
    action: str = "confirm"

class ActionCancelled(BaseModel):
    """Сигнал об отмене действия из текста"""
    action: str = "cancel"

class ContactInDB(BaseModel):
    id: UUID
    user_id: int
    name: str
    summary: str | None
    raw_text: str | None
    meta: dict
    created_at: datetime
    last_interaction: datetime | None
    reminder_at: datetime | None
    is_archived: bool
    
    model_config = ConfigDict(from_attributes=True)

class SearchResult(BaseModel):
    id: UUID
    name: str
    summary: str | None
    meta: dict
    distance: float | None = None
