#!/usr/bin/env python
# /// script
# requires-python = ">=3.11"
# requires = ["flask", "requests"]
# dependencies = [
#     "flask",
#     "requests",
# ]
# ///
"""
A Flask-based proxy server for the Gemini API.

This script intercepts requests intended for the Gemini API, logs the request
and response to a local directory, and then forwards the request to the actual
Gemini API endpoint. It's designed to be a transparent interceptor for debugging
and analysis purposes.

The server listens on the endpoints specified in the Gemini API documentation
and mirrors the behavior of the actual API.

Endpoints supported:
- POST /v1beta/models/{model}:generateContent
- POST /v1beta/models/{model}:streamGenerateContent
- POST /v1beta/models/{model}:countTokens
- POST /v1beta/models/{model}:embedContent

Usage:
    uv run proxy_interceptor.py [--port=PORT]

Default port is 8099.
"""

import argparse
import json
import os
import time
from flask import Flask, request, Response, stream_with_context
import requests

# --- Configuration ---
# The base URL for the real Gemini API
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"

# Absolute path for storing request/response logs
LOG_DIRECTORY = os.path.join(os.getcwd(), "inter_logs")

# --- Flask App Initialization ---
app = Flask(__name__)


def get_forwarding_headers():
    """
    Extracts relevant headers from the incoming request to forward to the Gemini API.
    """
    headers = {}
    # Forward essential headers
    headers_to_forward = [
        'x-goog-api-key',
        'authorization', 
        'content-type',
        'x-goog-api-client',
        'x-gemini-api-privileged-user-id',
        'user-agent',
        'accept',
        'accept-language',
        'accept-encoding'
    ]
    
    for header_name in headers_to_forward:
        # Check both lowercase and original case
        if header_name in request.headers:
            headers[header_name] = request.headers[header_name]
        elif header_name.lower() in [h.lower() for h in request.headers.keys()]:
            # Find the actual header name with correct case
            for actual_header in request.headers.keys():
                if actual_header.lower() == header_name.lower():
                    headers[actual_header] = request.headers[actual_header]
                    break
    
    return headers


def log_request_response(
    incoming_request,
    outgoing_response,
    response_body,
    epoch_time
):
    """
    Logs the full request and response to separate JSON files.
    """
    if not os.path.exists(LOG_DIRECTORY):
        os.makedirs(LOG_DIRECTORY)

    # Log request
    req_log_filename = f"{epoch_time}-request.json"
    req_log_filepath = os.path.join(LOG_DIRECTORY, req_log_filename)
    request_log = {
        "method": incoming_request.method,
        "url": incoming_request.url,
        "headers": dict(incoming_request.headers),
        "body": incoming_request.get_json()
    }
    with open(req_log_filepath, 'w') as f:
        json.dump(request_log, f, indent=2)

    # Log response
    res_log_filename = f"{epoch_time}-response.json"
    res_log_filepath = os.path.join(LOG_DIRECTORY, res_log_filename)
    response_log = {
        "statusCode": outgoing_response.status_code,
        "headers": dict(outgoing_response.headers),
        "body": response_body
    }
    with open(res_log_filepath, 'w') as f:
        json.dump(response_log, f, indent=2)


@app.route('/v1beta/models/<path:model>:<string:action>', methods=['POST'])
def proxy_request(model, action):
    """
    Handles all non-streaming requests to the Gemini API.
    """
    # Construct the full URL for the Gemini API with all query parameters
    gemini_url = f"{GEMINI_API_BASE_URL}/v1beta/models/{model}:{action}"
    
    # Forward all query parameters from the original request
    if request.args:
        query_params = []
        for key, value in request.args.items():
            query_params.append(f"{key}={value}")
        gemini_url += "?" + "&".join(query_params)
    
    # Get the request body and headers
    epoch_time = int(time.time())
    request_body = request.get_json()
    forward_headers = get_forwarding_headers()

    # Forward the request to the Gemini API
    response = requests.post(
        gemini_url,
        json=request_body,
        headers=forward_headers
    )

    # Log the request and response
    try:
        response_body = response.json()
    except json.JSONDecodeError:
        response_body = response.text
    log_request_response(request, response, response_body, epoch_time)

    # Return the response to the client
    # Filter out headers that could cause issues when proxying
    filtered_headers = {}
    seen_headers = set()
    for key, value in response.headers.items():
        key_lower = key.lower()
        # Skip headers that Flask/Werkzeug should handle or that could cause conflicts
        if key_lower not in ['content-length', 'transfer-encoding', 'connection', 'server', 'date', 'content-encoding']:
            # Avoid duplicate headers (case-insensitive check)
            if key_lower not in seen_headers:
                filtered_headers[key] = value
                seen_headers.add(key_lower)
    
    return Response(
        response.content,
        status=response.status_code,
        headers=filtered_headers
    )

@app.route('/v1beta/models/<path:model>:streamGenerateContent', methods=['POST'])
def proxy_streaming_request(model):
    """
    Handles streaming requests to the Gemini API.
    """
    # Construct the full URL for the Gemini API with all query parameters
    gemini_url = f"{GEMINI_API_BASE_URL}/v1beta/models/{model}:streamGenerateContent"
    
    # Forward all query parameters from the original request
    if request.args:
        query_params = []
        for key, value in request.args.items():
            query_params.append(f"{key}={value}")
        gemini_url += "?" + "&".join(query_params)
    
    epoch_time = int(time.time())
    forward_headers = get_forwarding_headers()

    # Log the request immediately
    if not os.path.exists(LOG_DIRECTORY):
        os.makedirs(LOG_DIRECTORY)
        
    req_log_filename = f"{epoch_time}-request.json"
    req_log_filepath = os.path.join(LOG_DIRECTORY, req_log_filename)
    request_log = {
        "method": request.method,
        "url": request.url,
        "headers": dict(request.headers),
        "body": request.get_json()
    }
    with open(req_log_filepath, 'w') as f:
        json.dump(request_log, f, indent=2)

    # Use stream=True to handle the streaming response
    response = requests.post(
        gemini_url,
        json=request.get_json(),
        headers=forward_headers,
        stream=True
    )

    def generate():
        """A generator function to stream the response content."""
        full_response_text = ""
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:  # filter out keep-alive chunks
                full_response_text += chunk.decode('utf-8', errors='ignore')
                yield chunk
        
        # Log the full response after the stream is complete
        res_log_filename = f"{epoch_time}-response.json"
        res_log_filepath = os.path.join(LOG_DIRECTORY, res_log_filename)
        
        # Handle different response formats
        body_to_log = full_response_text
        if full_response_text.strip():
            try:
                # Try to parse as JSON lines (Server-Sent Events format)
                lines = [line.strip() for line in full_response_text.strip().split('\n') if line.strip()]
                if lines and lines[0].startswith('data: '):
                    # Parse SSE format
                    json_objects = []
                    for line in lines:
                        if line.startswith('data: '):
                            try:
                                json_obj = json.loads(line[6:])  # Remove 'data: ' prefix
                                json_objects.append(json_obj)
                            except json.JSONDecodeError:
                                pass
                    if json_objects:
                        body_to_log = json_objects
                else:
                    # Try to parse as regular JSON
                    try:
                        body_to_log = json.loads(full_response_text)
                    except json.JSONDecodeError:
                        pass
            except Exception:
                # Fallback to raw text
                pass

        response_log = {
            "statusCode": response.status_code,
            "headers": dict(response.headers),
            "body": body_to_log
        }
        with open(res_log_filepath, 'w') as f:
            json.dump(response_log, f, indent=2)

    # Filter out problematic headers for streaming
    filtered_headers = {}
    seen_headers = set()
    for key, value in response.headers.items():
        key_lower = key.lower()
        # Skip headers that could cause streaming issues or conflicts
        if key_lower not in ['content-length', 'transfer-encoding', 'connection', 'server', 'date', 'content-encoding']:
            # Avoid duplicate headers (case-insensitive check)
            if key_lower not in seen_headers:
                filtered_headers[key] = value
                seen_headers.add(key_lower)
    
    # Use stream_with_context to stream the response back to the client
    return Response(
        stream_with_context(generate()),
        status=response.status_code,
        headers=filtered_headers
    )


if __name__ == '__main__':
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Gemini API Proxy Interceptor")
    parser.add_argument(
        '--port',
        type=int,
        default=8099,
        help='Port to run the server on (default: 8099)'
    )
    parser.add_argument(
        '--no-reload',
        dest='reload',
        action='store_false',
        help='Disable auto-reloading on code changes.'
    )
    parser.set_defaults(reload=True)
    args = parser.parse_args()

    # Ensure the log directory exists
    if not os.path.exists(LOG_DIRECTORY):
        os.makedirs(LOG_DIRECTORY)
        print(f"Created log directory: {LOG_DIRECTORY}")

    # Run the Flask app
    app.run(host='0.0.0.0', port=args.port, debug=args.reload)
