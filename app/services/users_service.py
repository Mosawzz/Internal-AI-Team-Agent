
from app.db.database import SessionLocal
from app.db.models import User
from app.errors import ValidationError, NotFoundError


def list_users() -> list[User]:
    """Return all users ordered by ID."""

    db = SessionLocal()

    try:
        users = (
            db.query(User)
            .order_by(User.id.asc())
            .all()
        )

        return users

    finally:
        db.close()


def get_user(user_id: int) -> User:
    """Return one user by ID."""

    # Validate before querying the database
    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        raise ValidationError("Invalid user ID.")

    db = SessionLocal()

    try:
        user = db.get(User, user_id)

        if user is None:
            raise NotFoundError(
                f"User with ID {user_id} was not found."
            )

        return user

    finally:
        db.close()
