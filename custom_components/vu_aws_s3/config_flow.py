"""Config flow for the AWS S3 Folder integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from aiobotocore.session import AioSession
from botocore.exceptions import ClientError, ConnectionError, ParamValidationError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    AWS_DOMAIN,
    CONF_ACCESS_KEY_ID,
    CONF_BUCKET,
    CONF_ENDPOINT_URL,
    CONF_PATH,
    CONF_SECRET_ACCESS_KEY,
    DEFAULT_ENDPOINT_URL,
    DEFAULT_PATH,
    DESCRIPTION_AWS_S3_DOCS_URL,
    DESCRIPTION_BOTO3_DOCS_URL,
    DOMAIN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_KEY_ID): cv.string,
        vol.Required(CONF_SECRET_ACCESS_KEY): TextSelector(
            config=TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_BUCKET): cv.string,
        vol.Required(CONF_ENDPOINT_URL, default=DEFAULT_ENDPOINT_URL): TextSelector(
            config=TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Optional(CONF_PATH, default=DEFAULT_PATH): cv.string,
    }
)


class S3FolderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {
                    CONF_BUCKET: user_input[CONF_BUCKET],
                    CONF_ENDPOINT_URL: user_input[CONF_ENDPOINT_URL],
                    CONF_PATH: user_input.get(CONF_PATH, DEFAULT_PATH),
                }
            )

            # 確保路徑是有效格式的 S3 路徑 (不以 '/' 開頭，但可以以 '/' 結尾)
            path = user_input.get(CONF_PATH, DEFAULT_PATH)
            if path and path.startswith("/"):
                errors[CONF_PATH] = "invalid_path_format"
            else:
                # 確保路徑如果不為空則以 '/' 結尾
                if path and not path.endswith("/"):
                    user_input[CONF_PATH] = f"{path}/"
                
                if not urlparse(user_input[CONF_ENDPOINT_URL]).hostname.endswith(
                    AWS_DOMAIN
                ):
                    errors[CONF_ENDPOINT_URL] = "invalid_endpoint_url"
                else:
                    try:
                        session = AioSession()
                        async with session.create_client(
                            "s3",
                            endpoint_url=user_input.get(CONF_ENDPOINT_URL),
                            aws_secret_access_key=user_input[CONF_SECRET_ACCESS_KEY],
                            aws_access_key_id=user_input[CONF_ACCESS_KEY_ID],
                        ) as client:
                            await client.head_bucket(Bucket=user_input[CONF_BUCKET])
                    except ClientError:
                        errors["base"] = "invalid_credentials"
                    except ParamValidationError as err:
                        if "Invalid bucket name" in str(err):
                            errors[CONF_BUCKET] = "invalid_bucket_name"
                    except ValueError:
                        errors[CONF_ENDPOINT_URL] = "invalid_endpoint_url"
                    except ConnectionError:
                        errors[CONF_ENDPOINT_URL] = "cannot_connect"
                    else:
                        # 設置標題，如果有路徑則包含路徑
                        title = user_input[CONF_BUCKET]
                        if path := user_input.get(CONF_PATH):
                            title = f"{title}/{path}"
                        
                        return self.async_create_entry(
                            title=title, data=user_input
                        )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders={
                "aws_s3_docs_url": DESCRIPTION_AWS_S3_DOCS_URL,
                "boto3_docs_url": DESCRIPTION_BOTO3_DOCS_URL,
            },
        )