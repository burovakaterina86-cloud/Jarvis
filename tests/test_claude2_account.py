"""Настройка входа: никакие данные аккаунта не попадают в вывод проверки."""
from scripts import claude2_account


def test_status_summary_does_not_reveal_identity():
    primary = {"loggedIn": True, "email": "first@example.test"}
    second = {"loggedIn": True, "email": "second@example.test", "authMethod": "claude.ai", "subscriptionType": "max"}
    result = claude2_account.summary(primary, second)
    assert result == {"logged_in": True, "subscription_login": True, "different_account": True}
    assert "example" not in str(result)
    second["email"] = primary["email"]
    assert claude2_account.summary(primary, second)["different_account"] is False
