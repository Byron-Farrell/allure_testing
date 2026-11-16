import allure
import json
from django.test import Client


@allure.feature("Health")
def test_health_returns_ok():
    client = Client()

    with allure.step("GET /api/health"):
        response = client.get("/api/health", HTTP_HOST="localhost")

    with allure.step("Response status is 200"):
        assert response.status_code == 200

    with allure.step("Body is status ok"):
        assert response.json() == {"status": "ok"}
        allure.attach(json.dumps(response.json()), "Response body", allure.attachment_type.JSON)