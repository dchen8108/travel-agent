from __future__ import annotations

from app.services.gmail_client import authorize_gmail
from app.settings import get_settings


def main() -> None:
    token_path = authorize_gmail(get_settings())
    print(f"Gmail booking auth complete. Token saved to {token_path}")


if __name__ == "__main__":
    main()

