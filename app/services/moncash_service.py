import httpx
from ..config import get_settings

settings = get_settings()
TOKEN_URL = "https://sandbox.moncashbutton.digicelgroup.com/Api/oauth/token"
PAYMENT_URL = "https://sandbox.moncashbutton.digicelgroup.com/Api/v1/CreatePayment"


async def create_payment(amount: float, order_id: str) -> dict:
    """Kreye yon peman MonCash. Mete kredansyel ou nan .env pou li mache."""
    if not settings.MONCASH_CLIENT_ID:
        return {"success": False, "message": "MonCash pa konfigire. Mete MONCASH_CLIENT_ID nan .env"}
    async with httpx.AsyncClient() as client:
        token = await client.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": settings.MONCASH_CLIENT_ID,
            "client_secret": settings.MONCASH_CLIENT_SECRET,
        })
        access = token.json()["access_token"]
        res = await client.post(PAYMENT_URL,
            headers={"Authorization": f"Bearer {access}"},
            json={"amount": amount, "orderId": order_id})
        return res.json()