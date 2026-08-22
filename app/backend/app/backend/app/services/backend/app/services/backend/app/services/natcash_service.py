import httpx
from app.config import settings

class NatCashService:
    def __init__(self):
        self.base_url = settings.kobara_base_url
        self.api_key = settings.kobara_api_key
    
    async def create_payment(self, amount: float, reference: str):
        url = f"{self.base_url}/payments"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={
                "amount": amount,
                "reference": reference,
                "currency": "HTG"
            }, headers={"Authorization": f"Bearer {self.api_key}"})
            return resp.json()

natcash_service = NatCashService()