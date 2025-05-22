from flask import Flask, jsonify, request
import os, time, random, threading, requests

# Config vars
SERVICE_NAME = os.environ.get("SERVICE_NAME", "default")
VERSION = os.environ.get("VERSION", "v1")
CALLS = os.environ.get("CALLS", "")
DELAY = float(os.environ.get("DELAY", "0"))
FAIL_RATE = float(os.environ.get("FAIL_RATE", "0"))
ENABLE_TRACING = os.environ.get("ENABLE_TRACING", "false").lower() == "true"
JAEGER_ENDPOINT = os.environ.get("JAEGER_ENDPOINT", "http://jaeger:4318/v1/traces")

# Tracing setup
if ENABLE_TRACING:
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME as OTEL_SERVICE_NAME
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.context import attach, detach, get_current
    from opentelemetry.propagate import inject

    trace.set_tracer_provider(
        TracerProvider(
            resource=Resource.create({OTEL_SERVICE_NAME: SERVICE_NAME})
        )
    )
    tracer = trace.get_tracer(__name__)
    span_processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=JAEGER_ENDPOINT))
    trace.get_tracer_provider().add_span_processor(span_processor)

app = Flask(__name__)

if ENABLE_TRACING:
    FlaskInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()

# Function that calls other services
def call_service(name, result, context):
    try:
        token = attach(context)
        headers = {}
        inject(headers)  # Inject tracing headers into request

        res = requests.get(f'http://{name}:5000/', headers=headers)
        result[name] = res.json()
    except Exception as e:
        result[name] = {"error": str(e)}
    finally:
        detach(token)

@app.route('/')
def index():
    time.sleep(DELAY)

    if random.random() < FAIL_RATE:
        return jsonify({"error": "simulated failure"}), 500

    children = {}
    threads = []

    if CALLS:
        current_context = get_current()
        for svc in CALLS.split(','):
            t = threading.Thread(target=call_service, args=(svc.strip(), children, current_context))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

    return jsonify({
        "service": SERVICE_NAME,
        "version": VERSION,
        "children": children
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)