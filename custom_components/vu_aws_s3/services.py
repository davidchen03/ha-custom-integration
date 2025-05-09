"""Services for AWS S3 Folder integration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import os
import tempfile
from typing import Any, cast

from botocore.exceptions import BotoCoreError, ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from . import S3FolderConfigEntry, join_path_elements
from .const import CONF_BUCKET, CONF_PATH, DEFAULT_PATH, DOMAIN

# 服務名稱
SERVICE_GET_FILE = "get_file"
SERVICE_PUT_FILE = "put_file"
SERVICE_DELETE_FILE = "delete_file"
SERVICE_LIST_FILES = "list_files"

# 服務參數
ATTR_FILENAME = "filename"
ATTR_PATH = "path"
ATTR_KEY = "key"
ATTR_PREFIX = "prefix"
ATTR_LOCAL_FILE = "local_file"
ATTR_CONTENT_TYPE = "content_type"
ATTR_DELIMITER = "delimiter"
ATTR_MAX_KEYS = "max_keys"

# 檔案內容類型預設值
DEFAULT_CONTENT_TYPE = "application/octet-stream"
DEFAULT_DELIMITER = "/"
DEFAULT_MAX_KEYS = 1000

# 服務定義
SCHEMA_GET_FILE = vol.Schema(
    {
        vol.Required(ATTR_KEY): cv.string,
        vol.Required(ATTR_LOCAL_FILE): cv.string,
    }
)

SCHEMA_PUT_FILE = vol.Schema(
    {
        vol.Required(ATTR_KEY): cv.string,
        vol.Required(ATTR_LOCAL_FILE): cv.string,
        vol.Optional(ATTR_CONTENT_TYPE, default=DEFAULT_CONTENT_TYPE): cv.string,
    }
)

SCHEMA_DELETE_FILE = vol.Schema(
    {
        vol.Required(ATTR_KEY): cv.string,
    }
)

SCHEMA_LIST_FILES = vol.Schema(
    {
        vol.Optional(ATTR_PREFIX): cv.string,
        vol.Optional(ATTR_DELIMITER, default=DEFAULT_DELIMITER): cv.string,
        vol.Optional(ATTR_MAX_KEYS, default=DEFAULT_MAX_KEYS): cv.positive_int,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for AWS S3 Folder integration."""

    @callback
    def get_client_for_call(call: ServiceCall) -> tuple[S3FolderConfigEntry, dict[str, Any]]:
        """Get an S3 client instance for the service call."""
        entries: list[S3FolderConfigEntry] = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(
                f"No configured {DOMAIN} entries found",
                translation_domain=DOMAIN,
                translation_key="no_configured_entries",
            )

        entry_id = call.data.get("entry_id")
        
        if entry_id:
            entry = next((entry for entry in entries if entry.entry_id == entry_id), None)
            if not entry:
                raise ServiceValidationError(
                    f"No {DOMAIN} entry found with id {entry_id}",
                    translation_domain=DOMAIN,
                    translation_key="entry_not_found",
                )
        else:
            entry = entries[0]  # 使用第一個設定項
        
        # 確保 entry 已載入
        if not entry.state.recoverable:
            raise ServiceValidationError(
                f"{DOMAIN} integration is not loaded",
                translation_domain=DOMAIN,
                translation_key="integration_not_loaded",
            )
        
        client = cast(S3FolderConfigEntry, entry).runtime_data
        return entry, client

    async def handle_get_file(call: ServiceCall) -> None:
        """Handle the get_file service call."""
        entry, client = get_client_for_call(call)
        
        key = call.data[ATTR_KEY]
        local_file = call.data[ATTR_LOCAL_FILE]
        
        # 將用戶的相對路徑轉換為絕對路徑
        if not os.path.isabs(local_file):
            local_file = hass.config.path(local_file)
        
        # 確保目標目錄存在
        os.makedirs(os.path.dirname(local_file), exist_ok=True)
        
        # 將 key 與設定的路徑結合
        base_path = entry.data.get(CONF_PATH, DEFAULT_PATH)
        full_key = join_path_elements(base_path, key)
        
        try:
            # 建立臨時檔案，避免下載中斷造成的問題
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_path = temp_file.name
            
            response = await client.get_object(
                Bucket=entry.data[CONF_BUCKET], 
                Key=full_key
            )
            
            # 從響應中讀取內容並寫入臨時檔案
            async with response["Body"] as stream:
                with open(temp_path, "wb") as temp_file:
                    async for chunk in stream.iter_chunks():
                        temp_file.write(chunk)
            
            # 移動臨時檔案到目標位置
            os.replace(temp_path, local_file)
        
        except (BotoCoreError, ClientError) as err:
            # 清理臨時檔案
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
            raise HomeAssistantError(
                f"Error downloading file from S3: {err}"
            ) from err

    async def handle_put_file(call: ServiceCall) -> None:
        """Handle the put_file service call."""
        entry, client = get_client_for_call(call)
        
        key = call.data[ATTR_KEY]
        local_file = call.data[ATTR_LOCAL_FILE]
        content_type = call.data.get(ATTR_CONTENT_TYPE, DEFAULT_CONTENT_TYPE)
        
        # 將用戶的相對路徑轉換為絕對路徑
        if not os.path.isabs(local_file):
            local_file = hass.config.path(local_file)
        
        # 檢查檔案是否存在
        if not os.path.isfile(local_file):
            raise ServiceValidationError(
                f"File {local_file} does not exist",
                translation_domain=DOMAIN,
                translation_key="file_not_found",
            )
        
        # 將 key 與設定的路徑結合
        base_path = entry.data.get(CONF_PATH, DEFAULT_PATH)
        full_key = join_path_elements(base_path, key)
        
        try:
            # 讀取檔案內容
            with open(local_file, "rb") as file:
                file_data = file.read()
            
            # 上傳到 S3
            await client.put_object(
                Bucket=entry.data[CONF_BUCKET],
                Key=full_key,
                Body=file_data,
                ContentType=content_type,
            )
        
        except (BotoCoreError, ClientError) as err:
            raise HomeAssistantError(
                f"Error uploading file to S3: {err}"
            ) from err

    async def handle_delete_file(call: ServiceCall) -> None:
        """Handle the delete_file service call."""
        entry, client = get_client_for_call(call)
        
        key = call.data[ATTR_KEY]
        
        # 將 key 與設定的路徑結合
        base_path = entry.data.get(CONF_PATH, DEFAULT_PATH)
        full_key = join_path_elements(base_path, key)
        
        try:
            await client.delete_object(
                Bucket=entry.data[CONF_BUCKET],
                Key=full_key,
            )
        
        except (BotoCoreError, ClientError) as err:
            raise HomeAssistantError(
                f"Error deleting file from S3: {err}"
            ) from err

    async def handle_list_files(call: ServiceCall) -> dict[str, Any]:
        """Handle the list_files service call."""
        entry, client = get_client_for_call(call)
        
        # 獲取參數
        base_path = entry.data.get(CONF_PATH, DEFAULT_PATH)
        prefix = call.data.get(ATTR_PREFIX, "")
        delimiter = call.data.get(ATTR_DELIMITER, DEFAULT_DELIMITER)
        max_keys = call.data.get(ATTR_MAX_KEYS, DEFAULT_MAX_KEYS)
        
        # 將 prefix 與設定的路徑結合
        full_prefix = join_path_elements(base_path, prefix)
        
        try:
            response = await client.list_objects_v2(
                Bucket=entry.data[CONF_BUCKET],
                Prefix=full_prefix,
                Delimiter=delimiter,
                MaxKeys=max_keys,
            )
            
            # 提取檔案和資料夾資訊
            result = {
                "files": [],
                "prefixes": [],
            }
            
            # 處理檔案
            for item in response.get("Contents", []):
                key = item["Key"]
                
                # 移除基本路徑前綴以顯示相對路徑
                if base_path and key.startswith(base_path):
                    rel_key = key[len(base_path):]
                else:
                    rel_key = key
                
                result["files"].append({
                    "key": rel_key,
                    "size": item["Size"],
                    "last_modified": item["LastModified"].isoformat(),
                })
            
            # 處理資料夾（通用前綴）
            for prefix in response.get("CommonPrefixes", []):
                prefix_key = prefix["Prefix"]
                
                # 移除基本路徑前綴以顯示相對路徑
                if base_path and prefix_key.startswith(base_path):
                    rel_prefix = prefix_key[len(base_path):]
                else:
                    rel_prefix = prefix_key
                
                result["prefixes"].append(rel_prefix)
            
            return result
        
        except (BotoCoreError, ClientError) as err:
            raise HomeAssistantError(
                f"Error listing files from S3: {err}"
            ) from err

    # 註冊服務
    hass.services.async_register(
        DOMAIN, SERVICE_GET_FILE, handle_get_file, schema=SCHEMA_GET_FILE
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PUT_FILE, handle_put_file, schema=SCHEMA_PUT_FILE
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_FILE, handle_delete_file, schema=SCHEMA_DELETE_FILE
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LIST_FILES, handle_list_files, schema=SCHEMA_LIST_FILES
    )