from ninja import NinjaAPI, Schema

api = NinjaAPI()


class HealthOut(Schema):
    status: str


@api.get("/health", response=HealthOut)
def health(request):
    return {"status": "ok"}
