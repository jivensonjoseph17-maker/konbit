
from ..config import get_settings

settings = get_settings()


async def create_payment(amount: float, reference: str) -> dict:
    """Kreye yon peman NatCash. Ranplase ak API reyèl NatCash la."""
    if not settings.NATCASH_API_KEY:
        return {"success": False, "message": "NatCash pa konfigire. Mete NATCASH_API_KEY nan .env"}
    return {"success": True, "reference": reference, "amount": amount}