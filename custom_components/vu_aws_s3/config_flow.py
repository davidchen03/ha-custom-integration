"""Config flow for the AWS S3 Folder integration."""

from __future__ import annotations

import logging
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

_LOGGER = logging.getLogger(__name__)

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
        """Handle user input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {
                    CONF_BUCKET: user_input[CONF_BUCKET],
                    CONF_ENDPOINT_URL: user_input[CONF_ENDPOINT_URL],
                    CONF_PATH: user_input.get(CONF_PATH, DEFAULT_PATH),
                }
            )

            path = user_input.get(CONF_PATH, DEFAULT_PATH)
            if path and path.startswith("/"):
                errors[CONF_PATH] = "invalid_path_format"
            else:
                if path and not path.endswith("/"):
                    path += "/"
                    user_input[CONF_PATH] = path

                endpoint_url = user_input[CONF_ENDPOINT_URL]
                hostname = urlparse(endpoint_url).hostname

                if not hostname or not hostname.endswith(AWS_DOMAIN):
                    _LOGGER.error("Invalid endpoint URL: %s, hostname: %s", endpoint_url, hostname)
                    errors[CONF_ENDPOINT_URL] = "invalid_endpoint_url"
                else:
                    _LOGGER.debug(
                        "Attempting to connect to AWS S3: %s, bucket: %s, path: %s",
                        endpoint_url,
                        user_input[CONF_BUCKET],
                        path,
                    )
                    try:
                        session = AioSession()
                        async with session.create_client(
                            "s3",
                            endpoint_url=endpoint_url,
                            aws_secret_access_key=user_input[CONF_SECRET_ACCESS_KEY],
                            aws_access_key_id=user_input[CONF_ACCESS_KEY_ID],
                            region_name=endpoint_url.split(".")[1] if "." in endpoint_url else None,
                        ) as client:
                            result = await client.list_objects_v2(
                                Bucket=user_input[CONF_BUCKET],
                                Prefix=path,
                                MaxKeys=1
                            )
                            _LOGGER.debug("list_objects_v2 result: %s", result)
                    except ClientError as err:
                        _LOGGER.error("AWS credentials or bucket/prefix error: %s", str(err))
                        errors["base"] = "invalid_credentials"
                    except ParamValidationError as err:
                        _LOGGER.error("Parameter validation error: %s", str(err))
                        if "Invalid bucket name" in str(err):
                            errors[CONF_BUCKET] = "invalid_bucket_name"
                        else:
                            errors["base"] = "param_validation_error"
                    except ValueError as err:
                        _LOGGER.error("Value error: %s", str(err))
                        errors[CONF_ENDPOINT_URL] = "invalid_endpoint_url"
                    except ConnectionError as err:
                        _LOGGER.error("Connection error: %s", str(err))
                        errors[CONF_ENDPOINT_URL] = "cannot_connect"
                    except Exception as err:  # pylint: disable=broad-except
                        _LOGGER.exception("Unexpected error: %s", str(err))
                        errors["base"] = "unknown_error"
                    else:
                        title = f"{user_input[CONF_BUCKET]}/{path}" if path else user_input[CONF_BUCKET]
                        return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_DATA_SCHEMA, user_input),
            errors=errors,
            description_placeholders={
                "aws_s3_docs_url": DESCRIPTION_AWS_S3_DOCS_URL,
                "boto3_docs_url": DESCRIPTION_BOTO3_DOCS_URL,
            },
        )

