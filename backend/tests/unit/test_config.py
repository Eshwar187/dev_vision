from app.core.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.APP_NAME == "DevVision AI"
    assert settings.ENVIRONMENT in ("development", "test", "production")
    assert settings.API_V1_STR == "/api/v1"
    assert len(settings.BACKEND_CORS_ORIGINS) > 0


def test_cors_origin_parsing():
    settings = Settings(BACKEND_CORS_ORIGINS="http://localhost:3000,http://example.com")
    assert "http://localhost:3000" in settings.BACKEND_CORS_ORIGINS
    assert "http://example.com" in settings.BACKEND_CORS_ORIGINS
