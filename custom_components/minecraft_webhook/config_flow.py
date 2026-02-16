"""Config flow for Minecraft Webhook integration."""
from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_SERVER_NAME,
    CONF_WEBHOOK_ID,
    DOMAIN,
)


def _generate_webhook_id() -> str:
    """Generate a unique webhook ID."""
    return secrets.token_hex(16)


class MinecraftWebhookConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Minecraft Webhook."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            server_name = user_input[CONF_SERVER_NAME]

            # Check if a server with this name already exists
            for entry in self._async_current_entries():
                if entry.data.get(CONF_SERVER_NAME) == server_name:
                    errors["base"] = "server_exists"
                    break

            if not errors:
                # Generate a unique webhook ID
                webhook_id = _generate_webhook_id()

                return self.async_create_entry(
                    title=server_name,
                    data={
                        CONF_SERVER_NAME: server_name,
                        CONF_WEBHOOK_ID: webhook_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERVER_NAME): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MinecraftWebhookOptionsFlow:
        """Get the options flow for this handler."""
        return MinecraftWebhookOptionsFlow()


class MinecraftWebhookOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Minecraft Webhook."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get webhook URL
        webhook_id = self.config_entry.data.get(CONF_WEBHOOK_ID, "")
        webhook_url = webhook.async_generate_url(self.hass, webhook_id)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders={
                "webhook_url": webhook_url,
                "webhook_id": webhook_id,
            },
        )
