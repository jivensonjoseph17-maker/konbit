import httpx
from app.config import settings

class MonCashService:
    def __init__(self):
        self.base_url = settings.moncash_base_url
        self.client_id = settings.moncash_client_id
        self.client_secret = settings.moncash_client_secret
        self._token = None
    
    async def _get_token(self):
        if self._token:
            return self._token
        url = f"{self.base_url}/Api/oauth/token"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret
            })
            data = resp.json()
            self._token = data.get("access_token")
            return self._token
    
    async def create_payment(self, amount: float, order_id: str):
        token = await self._get_token()
        url = f"{self.base_url}/Api/v2/CreatePayment"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={
                "amount": str(amount),
                "orderId": order_id
            }, headers={"Authorization": f"Bearer {token}"})
            return resp.json()

moncash_service = MonCashService()