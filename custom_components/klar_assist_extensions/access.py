"""Reject invalid identities before module handling or delegation."""
from homeassistant.exceptions import HomeAssistantError


async def active_user(hass, context) -> bool:
    # Genuine HA system contexts are preserved, never synthesized from a user.
    if context.user_id is None:
        return True
    try:
        user = await hass.auth.async_get_user(context.user_id)
    except (HomeAssistantError, AttributeError):
        return False
    return user is not None and user.is_active
