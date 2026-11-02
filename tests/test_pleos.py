import json

import httpx
import pytest
import respx

from kiatracker.pleos import BASE_URL, PleosClient, PleosError, RateLimited

TOKEN_URL = f"{BASE_URL}/v1/auth/personal-token"
BATTERY_URL = f"{BASE_URL}/v1/vehicles/VIN1/batteries"


def token(value: str) -> httpx.Response:
    return httpx.Response(200, json={"data": {"accessToken": value}})


@respx.mock
def test_login_sends_credentials_and_brand():
    route = respx.post(TOKEN_URL).mock(return_value=token("t1"))
    PleosClient("id", "secret").login()
    request = route.calls.last.request
    assert json.loads(request.content) == {"clientId": "id", "clientSecret": "secret"}
    assert request.headers["Brand"] == "kia"


@respx.mock
def test_get_relogs_in_once_on_expired_token():
    respx.post(TOKEN_URL).mock(side_effect=[token("old"), token("new")])
    respx.get(BATTERY_URL).mock(side_effect=[
        httpx.Response(400, json={"error": {"code": "40003", "message": "Token expired"}}),
        httpx.Response(200, json={"data": {"charge": {}}}),
    ])
    status, payload = PleosClient("id", "secret").get("/v1/vehicles/VIN1/batteries")
    assert status == 200
    assert respx.calls[-1].request.headers["Authorization"] == "Bearer new"


@respx.mock
def test_rate_limit_raises():
    respx.post(TOKEN_URL).mock(return_value=token("t"))
    respx.get(BATTERY_URL).mock(return_value=httpx.Response(429, text="slow down"))
    with pytest.raises(RateLimited):
        PleosClient("id", "secret").get("/v1/vehicles/VIN1/batteries")


@respx.mock
def test_failed_login_raises_with_code():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(404, json={"error": {"code": "40404"}}))
    with pytest.raises(PleosError) as err:
        PleosClient("id", "bad").login()
    assert err.value.status == 404
    assert err.value.code == "40404"


@respx.mock
def test_non_json_body_is_wrapped():
    respx.post(TOKEN_URL).mock(return_value=token("t"))
    respx.get(BATTERY_URL).mock(return_value=httpx.Response(502, text="<html>bad gateway</html>"))
    status, payload = PleosClient("id", "secret").get("/v1/vehicles/VIN1/batteries")
    assert status == 502
    assert payload == {"non_json_body": "<html>bad gateway</html>"}


@respx.mock
def test_vehicles_returns_list():
    respx.post(TOKEN_URL).mock(return_value=token("t"))
    respx.get(f"{BASE_URL}/v1/vehicles/consent").mock(
        return_value=httpx.Response(200, json={"data": {"vehicles": [{"vin": "VIN1", "sellname": "EV3"}]}}))
    assert PleosClient("id", "secret").vehicles() == [{"vin": "VIN1", "sellname": "EV3"}]
