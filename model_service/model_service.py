import argparse
import logging
import importlib
import requests

from pytriton.triton import Triton, TritonConfig


logger = logging.getLogger("kaleidoscope.model_service")
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(name)s: %(message)s")


def initialize_model(model_type):
    #try:
    return importlib.import_module(f"models.{model_type}.model").Model(model_type)
    # except:
    #     logger.error(f"Could not import model {model_type}")

class ModelService():

    def __init__(self, model_type, model_path, gateway_host, gateway_port, master_port) -> None:
        self.model_type = model_type
        self.gateway_host = gateway_host
        self.gateway_port = gateway_port
        self.master_port = master_port
        self.model_path = model_path

    def run(self):

        # Register model with gateway
        #logger.info(f"Registering model {self.model_type} with gateway")
        #gateway_service = GatewayService(self.gateway_host, self.gateway_port)
        #gateway_service.register_model(self.model_type, self.master_host, self.master_port)

        model = initialize_model(self.model_type)
        model.load(self.model_path)

        if model.rank == 0:
            logger.info(f"Starting model service for {self.model_type} on rank {model.rank}")

            #Placeholder static triton config for now
            triton_config = TritonConfig(http_address="0.0.0.0", http_port=8003, log_verbose=4)
            with Triton(config=triton_config) as triton:
                triton = model.bind(triton)
                triton.serve()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model_type",
        required=True,
        type=str,
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
    parser.add_argument(
        "--master_port", required=False, type=int, help="Port for device communication", default=29400
    )
    args = parser.parse_args()

    model_service = ModelService(args.model_type, args.model_path, args.gateway_host, args.gateway_port, args.master_port)
    model_service.run()


if __name__ == "__main__":
    main()
