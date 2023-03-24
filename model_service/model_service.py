import argparse
import flask
import requests
import signal
import socket
import sys
import torch
import os

from flask import Flask, request, jsonify


# Globals

AVAILABLE_MODELS = ["OPT-175B", "OPT-6.7B", "GPT2"]


# Start the Flask service that will hand off requests to the model libraries

service = Flask(__name__)


@service.route("/health", methods=["GET"])
def health():
    return {"msg": "Still Alive"}, 200


@service.route("/module_names", methods=["GET"])
def module_names():
    result = model.module_names()
    return result


@service.route("/generate", methods=["POST"])
def generate_text():
    result = model.generate(request)
    return result


@service.route("/get_activations", methods=["POST"])
def get_activations():
    print(request)
    print(request.json)
    result = model.get_activations(request)
    return result


# We only want to load the model library that's being requested, not all of them
# TODO: Is there a way to make this happen automatically, without separate entries?


def initialize_model(model_type):
    if model_type == "OPT-175B" or model_type == "OPT-6.7B":
        from models import OPT

        return OPT.OPT()
    elif model_type == "GPT2":
        from models import GPT2
        return GPT2.GPT2()


# Signal handler to send a remove request to the gateway, if this service is killed by the system


def signal_handler(sig, frame):
    global model_type
    send_remove_request(model_type)
    sys.exit(0)


def send_remove_request(model_type, gateway_host):
    remove_url = f"http://{gateway_host}/models/{model_type}/remove"
    try:
        response = requests.delete(remove_url)
    except requests.ConnectionError as e:
        print(f"Connection error: {e}")
    except:
        print(f"Unknown error contacting gateway service at {config.GATEWAY_HOST}")


def register_model_instance(model_instance_id, model_host, gateway_host):

    print(f"Preparing model registration request")
    register_url = (
        f"http://{gateway_host}/models/instances/{model_instance_id}/register"
    )
    register_data = {"host": model_host}
    print(
        f"Sending model registration request to {register_url} with data: {register_data}"
    )
    try:
        response = requests.post(register_url, json=register_data)
        # HTTP error codes between 450 and 500 are custom to the kaleidoscope gateway
        if int(response.status_code) >= 450 and int(response.status_code) < 500:
            raise requests.HTTPError(response.content.decode("utf-8"))
    # If we fail to contact the gateway service, print an error but continue running anyway
    # TODO: HTTPError probably isn't the best way to catch custom errors
    except requests.HTTPError as e:
        print(e)
    except requests.ConnectionError as e:
        print(f"Connection error: {e}")
    except:
        print(f"Unknown error contacting gateway service at {gateway_host}")


def activate_model_instance(model_instance_id, gateway_host):
    activation_url = (
        f"http://{gateway_host}/models/instances/{model_instance_id}/activate"
    )
    print(f"Sending model activation request to {activation_url}")
    try:
        response = requests.post(activation_url)
    except:
        print(f"Model instance activation failed with status code {response.status_code}: {response.text}")
        print(f"Continuing to load model anyway, but it will not be accessible to any gateway services")


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model_type",
        required=True,
        type=str,
        help="Model type selected in the list: " + ", ".join(AVAILABLE_MODELS),
    )
    parser.add_argument(
        "--model_path", required=True, type=str, help="Path to pre-trained model"
    )
    parser.add_argument("--model_instance_id", required=True, type=str)
    parser.add_argument(
        "--gateway_host", required=False, type=str, help="Hostname of gateway service", default="llm.cluster.local"
    )
    parser.add_argument(
        "--gateway_port", required=False, type=int, help="Port of gateway service", default=3001
    )
    args = parser.parse_args()
    args.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Validate input arguments
    if args.model_type not in AVAILABLE_MODELS:
        print(
            f"Error: model type {args.model_type} is not supported. Please use one of the following: {', '.join(AVAILABLE_MODELS)}"
        )
        sys.exit(1)

    gateway_host = f"{args.gateway_host}:{args.gateway_port}"

    # Setup a global model instance
    global model, model_type

    model = initialize_model(args.model_type)
    model_instance_id = args.model_instance_id
    model_type = args.model_type

    # Determine the IP address for the head node of this model
    try:
        master_addr = os.environ['MASTER_ADDR']
    except:
        master_addr = "localhost"
        print("MASTER_ADDR not set, defaulting to localhost")
    model_port = 9001
    model_host = f'{master_addr}:{model_port}'

    # Models that only run on a single node should advertise their IP address instead of "localhost"
    if master_addr == "localhost":
        hostname = socket.gethostname()
        ip_addr = socket.gethostbyname(hostname)
        model_host = f"{ip_addr}:{model_port}"

    register_model_instance(model_instance_id, model_host, gateway_host)

    # Load the model into GPU memory
    print(f"Loading model into device {args.device}")
    model.load(args.device, args.model_path)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Now start the service. This will block until user hits Ctrl+C or the process gets killed by the system
    activate_model_instance(model_instance_id, gateway_host)
    print("Starting model service, press Ctrl+C to exit")
    service.run(host=model_host.split(":")[0], port=model_host.split(":")[1])

    # Inform the gateway service that we are shutting down and it should remove this model
    send_remove_request(args.model_type)


if __name__ == "__main__":
    main()
