import allure
from django.test import Client


@allure.feature("Health")
def test_health_returns_ok():
    client = Client()

    response = client.get("/api/health", HTTP_HOST="localhost")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
