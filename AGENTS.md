# Project

This API uses Django Ninja: an endpoint validates input, calls a service or selector, and returns. It does not hold business logic.

## Where logic lives

- **Services** — writes. Each entity has its own file, `services/<entity>.py`, with functions named `<entity>_<action>`.
- **Selectors** — reads. Each entity has its own file, `selectors/<entity>.py`, with the same naming style. List filters stay inside the selector.
- **Models** — each entity has its own file, `models/<entity>.py`. Simple properties, and `Model.clean` for checks on non-relational fields.

Logic does not belong in Ninja endpoints, schemas, `Model.save`, custom managers, or signals.

## Ninja

One function per operation, with Pydantic input and output schemas. Import the entity module so the endpoint name does not shadow the service:

```python
from apps.users.services import user

created = user.user_create(email=payload.email, name=payload.name)
```

Domain code lives in `backend/apps/<name>/` as `models/<entity>.py`, `services/<entity>.py`, `selectors/<entity>.py`, `api.py`, and `schemas.py`. Register the router from `backend/config/api.py`.

