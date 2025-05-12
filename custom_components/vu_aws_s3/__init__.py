"""The AWS S3 Folder integration."""

from __future__ import annotations

import logging
from typing import cast

from aiobotocore.client import AioBaseClient as S3Client
from aiobotocore.session import AioSession
from botocore.exceptions import ClientError, ConnectionError, ParamValidationError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .const import (
    CONF_ACCESS_KEY_ID,
    CONF_BUCKET,
    CONF_ENDPOINT_URL,
    CONF_PATH,
    CONF_SECRET_ACCESS_KEY,
    DATA_BACKUP_AGENT_LISTENERS,
    DEFAULT_PATH,
    DOMAIN,
)

type S3FolderConfigEntry = ConfigEntry[S3Client]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: S3FolderConfigEntry) -> bool:
    """Set up S3 Folder from a config entry."""

    data = cast(dict, entry.data)
    try:
        session = AioSession()
        client = await session.create_client(
            "s3",
            endpoint_url=data.get(CONF_ENDPOINT_URL),
            aws_secret_access_key=data[CONF_SECRET_ACCESS_KEY],
            aws_access_key_id=data[CONF_ACCESS_KEY_ID],
        ).__aenter__()

        # Process prefix path
        path = data.get(CONF_PATH, DEFAULT_PATH) or ""
        if path and not path.endswith("/"):
            path += "/"

        _LOGGER.debug("Validating list_objects_v2: bucket=%s, prefix=%s",
                      data[CONF_BUCKET], path)

        # Validate prefix permissions using list_objects_v2
        await client.list_objects_v2(
            Bucket=data[CONF_BUCKET],
            Prefix=path,
            MaxKeys=1,
        )

    except ClientError as err:
        _LOGGER.error("S3 credential error or unable to access specified prefix: %s", err)
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="invalid_credentials",
        ) from err
    except ParamValidationError as err:
        _LOGGER.error("Parameter validation error: %s", err)
        if "Invalid bucket name" in str(err):
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="invalid_bucket_name",
            ) from err
        raise
    except ValueError as err:
        _LOGGER.error("URL format error: %s", err)
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="invalid_endpoint_url",
        ) from err
    except ConnectionError as err:
        _LOGGER.error("Unable to connect to AWS S3: %s", err)
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
        ) from err

    # Store client to entry
    entry.runtime_data = client

    # Register services
    from . import services
    await services.async_setup_services(hass)

    # Backup agent listeners
    def notify_backup_listeners() -> None:
        for listener in hass.data.get(DATA_BACKUP_AGENT_LISTENERS, []):
            listener()

    entry.async_on_unload(entry.async_on_state_change(notify_backup_listeners))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: S3FolderConfigEntry) -> bool:
    """Unload a config entry."""
    client = entry.runtime_data
    await client.__aexit__(None, None, None)
    return True


def join_path_elements(base_path: str, *paths: str) -> str:
    """Join path elements for S3 keys.

    Ensures consistent joining with trailing slashes for base,
    and no leading slashes for components.
    """
    if not base_path:
        base = ""
    else:
        base = base_path if base_path.endswith("/") else f"{base_path}/"

    if not paths:
        return base

    path_parts = [p.strip("/") for p in paths if p]
    return f"{base}{'/'.join(path_parts)}"
