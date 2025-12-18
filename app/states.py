from aiogram.fsm.state import State, StatesGroup

class OnboardingStates(StatesGroup):
    waiting_for_bio = State()
    waiting_for_first_contact = State()




