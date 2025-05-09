"""The AWS S3 Folder integration."""

from __future__ import annotations

import logging
import os
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
        # pylint: disable-next=unnecessary-dunder-call
        client = await session.create_client(
            "s3",
            endpoint_url=data.get(CONF_ENDPOINT_URL),
            aws_secret_access_key=data[CONF_SECRET_ACCESS_KEY],
            aws_access_key_id=data[CONF_ACCESS_KEY_ID],
        ).__aenter__()
        
        # 檢查 bucket 是否可以訪問
        await client.head_bucket(Bucket=data[CONF_BUCKET])
        
        # 如果有指定路徑，檢查路徑是否可以訪問（列出該路徑下的物件）
        path = data.get(CONF_PATH, DEFAULT_PATH)
        if path:
            await client.list_objects_v2(
                Bucket=data[CONF_BUCKET],
                Prefix=path,
                MaxKeys=1,
            )
            
    except ClientError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="invalid_credentials",
        ) from err
    except ParamValidationError as err:
        if "Invalid bucket name" in str(err):
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="invalid_bucket_name",
            ) from err
    except ValueError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="invalid_endpoint_url",
        ) from err
    except ConnectionError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
        ) from err

    entry.runtime_data = client

    # 註冊服務
    from . import services

    await services.async_setup_services(hass)

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
    
    This function joins the base path with additional path elements,
    ensuring there are no double slashes and that the path correctly
    maintains trailing slashes as needed.
    """
    # 如果基本路徑是空的，跳過它
    if not base_path:
        base = ""
    else:
        # 確保基本路徑以 / 結尾
        base = base_path if base_path.endswith("/") else f"{base_path}/"
    
    if not paths:
        return base
    
    # 將所有部分連接起來，移除前導 /
    path_parts = [p.lstrip("/") for p in paths if p]
    
    # 如果沒有其他路徑元素，直接返回基礎路徑
    if not path_parts:
        return base
    
    # 連接所有路徑元素
    return f"{base}{''.join(path_parts)}"