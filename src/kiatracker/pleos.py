"""Client for the Pleos Vehicle Data API (Hyundai/Kia/Genesis EU Data Act API, private-user key).

Docs: https://document.pleos.ai/en/api-reference/vehicle-data-api/intro
"""

import httpx

BASE_URL = "https://api.pleos.ai"
SNAPSHOT_PATHS = {
    "batteries": "/v1/vehicles/{vin}/batteries",
    "powertrains": "/v1/vehicles/{vin}/powertrains",
    "locations": "/v1/vehicles/{vin}/locations",
    "driving": "/v1/vehicles/{vin}/driving",
    "status": "/v1/vehicles/{vin}/status",
}
# The only trip endpoint the EV3 supports; it returns start time and duration per trip.
TRIPS_PATH = "/v1/vehicles/{vin}/driving/data"
TOKEN_ERRORS = {"40003", "40004"}  # expired, invalid


class PleosError(Exception):
    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


class RateLimited(PleosError):
    pass


def error_code(payload: dict) -> str | None:
    error = payload.get("error") if isinstance(payload, dict) else None
    return str(error["code"]) if isinstance(error, dict) and "code" in error else None


def parse_body(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {"non_json_body": response.text[:500]}
    return body if isinstance(body, dict) else {"body": body}


class PleosClient:
    def __init__(
        self, client_id: str, client_secret: str, brand: str = "kia", http: httpx.Client | None = None
    ):
        self.credentials = {"clientId": client_id, "clientSecret": client_secret}
        self.http = http or httpx.Client(base_url=BASE_URL, timeout=30)
        self.http.headers["Brand"] = brand
        self.token: str | None = None

    def login(self) -> None:
        response = self.http.post("/v1/auth/personal-token", json=self.credentials)
        payload = parse_body(response)
        token = (payload.get("data") or {}).get("accessToken") if response.status_code == 200 else None
        if not token:
            raise PleosError("login failed", response.status_code, error_code(payload))
        self.token = token

    def _request(self, path: str, params: dict | None) -> httpx.Response:
        return self.http.get(path, params=params, headers={"Authorization": f"Bearer {self.token}"})

    def get(self, path: str, params: dict | None = None) -> tuple[int, dict]:
        if not self.token:
            self.login()
        response = self._request(path, params)
        if error_code(parse_body(response)) in TOKEN_ERRORS:
            self.login()
            response = self._request(path, params)
        if response.status_code == 429:
            raise RateLimited("rate limited", 429)
        return response.status_code, parse_body(response)

    def vehicles(self) -> list[dict]:
        status, payload = self.get("/v1/vehicles/consent")
        if status != 200:
            raise PleosError("could not list vehicles", status, error_code(payload))
        return (payload.get("data") or {}).get("vehicles") or []
