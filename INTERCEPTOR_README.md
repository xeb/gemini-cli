# Gemini CLI Proxy Interceptor

This document outlines the process of using the `proxy_interceptor.py` script to intercept and log network traffic from the `gemini-cli` project.

## How it Works

1.  The `proxy_interceptor.py` script runs a local Flask web server.
2.  The `gemini-cli` is launched with the `GEMINI_CLI_BASE_URL` environment variable set to the address of the local proxy (e.g., `http://localhost:8099`).
3.  The CLI, now pointing to the proxy, sends its API requests there instead of the default Google servers.
4.  The proxy receives the request, logs it to a file, forwards the identical request to the real Gemini API, receives the response, logs the response, and finally passes the response back to the CLI.

This setup allows for debugging and analysis of the communication between the CLI and the Gemini API.

## How to Run the Interceptor

### Prerequisites

- Python 3.11+
- `uv` (or `pip`)

### Installation

Install the required Python packages:

```bash
pip install flask requests
```

### Running the Server

To start the proxy server, run the following command in your terminal:

```bash
uv run proxy_interceptor.py
```

By default, the server runs on port `8099`. You can specify a different port using the `--port` flag:

```bash
uv run proxy_interceptor.py --port=5001
```

The server will automatically reload when you make changes to the script.

## Setting the `GEMINI_CLI_BASE_URL` Override

After the interceptor is running, you need to configure the Gemini CLI to use it. This is done by setting the `GEMINI_CLI_BASE_URL` environment variable.

In your terminal, export the variable with the address of your running interceptor:

```bash
export GEMINI_CLI_BASE_URL="http://localhost:8099"
```

(Replace `8099` with the port your proxy is running on if you specified a different one.)

Now, any `gemini-cli` commands you run in that terminal session will have their traffic routed through your local interceptor.

### Example Usage

With the proxy running on port `8099` and the environment variable set, you can run a command like this:

```bash
npm start -- -p "Your prompt here"
```

The request and response will be logged in the `inter_logs` directory.
