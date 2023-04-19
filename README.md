# Coffee machine demo

Keeps an eye on the clover coffee machine, and alerts if somebody forgets to rinse.

## Running

1. Install poetry.

``` shell
curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python -
```

1. Install dependencies.

``` shell
poetry install
```

1. Configure environment variables:

``` shell
export RTSP_URL=rtsp://...
export SLACK_WEBHOOK_URL=https://...
export GROUNDLIGHT_API_TOKEN=api_...
```

See [manual](https://code.groundlight.ai/python-sdk/docs/getting-started/api-tokens) for instructions on how to get the Groundlight API token.

For instructions on RTSP URLs look [here](https://github.com/groundlight/stream/blob/main/CAMERAS.md).

For instructions on setting up slack webhooks, see [here](https://api.slack.com/messaging/webhooks).

1. Run the script.

``` shell
poetry run python coffee_demo.py
```

