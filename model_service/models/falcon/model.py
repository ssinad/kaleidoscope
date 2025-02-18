"""Module for Falcon LLM configurations"""
import logging
import numpy as np
import json
import torch
import os
import pathlib
import pprint

from ..abstract_model import AbstractModel

from pytriton.decorators import batch
from pytriton.model_config import ModelConfig, Tensor
from accelerate import init_empty_weights, load_checkpoint_and_dispatch, infer_auto_device_map
from accelerate.utils.modeling import get_balanced_memory
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, GenerationConfig


logger = logging.getLogger("kaleidoscope.model_service.falcon")
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(name)s: %(message)s")


TORCH_DTYPE_MAP = {
    "bfloat16": torch.bfloat16,
    "float16": torch.float16,
}


class Model(AbstractModel):

    def __init__(self, model_type, model_variant):
        self.model_class = AutoModelForCausalLM
        self.model_path = None
        self.model_type = model_type
        self.model_variant = model_variant
        self.tokenizer_class = AutoTokenizer
        self.model = None
        self.tokenizer = None
        self.model_cfg = None
        self.tokenizer_cfg = None
        self.device = None
        self.model_cfg_path = str(pathlib.Path(__file__).parent.resolve())


    def load(self, model_path):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.load_model_cfg(os.path.join(self.model_cfg_path, "model_config.json"))

        if self.model_variant == "40b":
            local_rank = int(os.getenv("LOCAL_RANK", "0"))
            world_size = torch.cuda.device_count()
            logger.info(f"Rank: {local_rank}")
            logger.info(f"World size: {world_size}")

            logger.debug(f"Torch dtype: {self.model_cfg['torch_dtype']}")
            config = AutoConfig.from_pretrained(
               model_path, trust_remote_code=self.model_cfg["trust_remote_code"], torch_dtype=self.model_cfg["torch_dtype"])
            with init_empty_weights():
               model = self.model_class.from_config(config, trust_remote_code=self.model_cfg["trust_remote_code"], torch_dtype=self.model_cfg["torch_dtype"])
            model.tie_weights()

            # Configure memory per device and get device map
            max_memory = {idx: "40GiB" for idx in range(world_size)}
            max_memory.update({"cpu": "120GiB"})
            device_map = infer_auto_device_map(model, max_memory, no_split_module_classes=["MLP", "DecoderLayer"])
            logging.debug(f"Max memory: {max_memory}")
            logging.debug(f"Device map: {device_map}")

            self.model = load_checkpoint_and_dispatch(
               model, model_path, device_map=device_map, dtype=self.model_cfg["torch_dtype"]) 
        else:
            self.model = self.model_class.from_pretrained(model_path, **self.model_cfg) # TODO: .eval()?
            self.model.to(self.device)

        self.tokenizer = self.tokenizer_class.from_pretrained(model_path, **self.tokenizer_cfg)
        self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

        self.model_path = model_path


    def load_model_cfg(self, cfg_file):
        """Load model and tokenzer config"""
        model_name = f"{self.model_type}-{self.model_variant}"
        try:
            with open(cfg_file, "r") as cfg_f:
                cfg = json.load(cfg_f)
            self.model_cfg = cfg[model_name]["model"]
            self.tokenizer_cfg = cfg[model_name]["tokenizer"]
            self.model_cfg["torch_dtype"] = TORCH_DTYPE_MAP.get(self.model_cfg["torch_dtype"], torch.float32)
            logger.info(self.model_cfg)
            logger.info(self.tokenizer_cfg)
        except Exception as err:
            logger.error(f"Failed to load model configuration: {err}")


    def load_default_args(self, cfg_file, task_name):
        """Load default generation config"""
        try:
            with open(cfg_file, "r") as cfg_f:
                cfg = json.load(cfg_f)
            default_args = cfg["parameters"]
            logger.info(pprint.pformat(default_args))
            self.default_args = {k: v["default"][task_name] for k, v in default_args.items() if v["default"][task_name] is not None}
        except Exception as err:
            logger.error(f"Failed to load model default generation configuration: {err}")


    def bind(self, triton):
        triton.bind(
            model_name=f"{self.model_type}-{self.model_variant}",
            infer_func=self.infer,
            inputs=[
                Tensor(name="task", dtype=np.int64, shape=(1,)),
                Tensor(name="prompts", dtype=bytes, shape=(1,)),
                Tensor(name='max_tokens', dtype=np.int64, shape=(1,), optional=True),
                Tensor(name='min_tokens', dtype=np.int64, shape=(1,), optional=True),
                Tensor(name='temperature', dtype=np.float64, shape=(1,), optional=True),
                Tensor(name='top_p', dtype=np.float64, shape=(1,), optional=True),
                Tensor(name='top_k', dtype=np.int64, shape=(1,), optional=True),
                Tensor(name='do_sample', dtype=np.bool_, shape=(1,), optional=True),
            ],
            outputs=[
                Tensor(name="sequences", dtype=object, shape=(-1,)),
                Tensor(name="tokens", dtype=object, shape=(-1,)),
                Tensor(name="logprobs", dtype=np.float64, shape=(-1,)),
            ],
            config=ModelConfig(max_batch_size=8), # TODO: set based on device memory and model variant
        )
        return triton


    @property
    def rank(self):
        return 0


    @batch
    def infer(self, **inputs):
        """Generate sequences from a prompt"""
        self.load_default_args(os.path.join(self.model_cfg_path, "config.json"), "generate")
        return self.generate(inputs)


    def generate(self, inputs):
        # Encode prompts and get attention mask
        prompts = np.char.decode(inputs.pop("prompts").astype("bytes"), encoding="utf-8")
        prompts = np.squeeze(prompts, axis=-1).tolist()
        encoded_obj = self.tokenizer(prompts, return_tensors="pt", padding=True)
        encoded_prompts = encoded_obj.input_ids
        attn_mask = encoded_obj.attention_mask
        encoded_prompts = encoded_prompts.to(self.device)
        attn_mask = attn_mask.to(self.device)

        # Create generation config: Check the input parameters, and set default values if not present
        gen_cfg = GenerationConfig(
            min_new_tokens=inputs["min_tokens"][0][0] if "min_tokens" in inputs else self.default_args["min_tokens"],
            max_new_tokens=inputs["max_tokens"][0][0] if "max_tokens" in inputs else self.default_args["max_tokens"],
            temperature=inputs["temperature"][0][0] if "temperature" in inputs else self.default_args["temperature"],
            top_p=inputs["top_p"][0][0] if "top_p" in inputs else self.default_args["top_p"],
            top_k=int(inputs["top_k"][0][0]) if "top_k" in inputs else self.default_args["top_k"],
            do_sample=bool(inputs["do_sample"][0][0]) if "do_sample" in inputs else self.default_args["do_sample"]
        )
        
        # Run the generation
        input_tokens_size = encoded_prompts.size()[-1]
        input_ids = encoded_prompts if input_tokens_size != 0 else None
        outputs = self.model.generate(
            input_ids, 
            gen_cfg, 
            attention_mask=attn_mask, 
            return_dict_in_generate=True, output_scores=True)
        transition_scores = self.model.compute_transition_scores(
            outputs.sequences, outputs.scores, normalize_logits=True)
        generated_ids = outputs.sequences
        # remove input tokens
        generated_ids = generated_ids[:, input_tokens_size:]
        # replace token_id 0 with a special token so that it is removed while decoding - EOS
        generated_ids[generated_ids==0] = int(self.tokenizer.eos_token_id)
        generations = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)

        # Get logprobs of generated tokens
        tokens = []
        logprobs = []
        for sequence, probs in zip(generated_ids, transition_scores):
            sequence_tokens = []
            sequence_logprobs = []
            for token, prob in zip(sequence, probs):
                if token not in self.tokenizer.all_special_ids:
                    sequence_tokens.append(self.tokenizer.decode(token))
                    sequence_logprobs.append(prob.item())
            tokens.append(sequence_tokens)
            logprobs.append(sequence_logprobs)

        return {
            "sequences": np.array(generations, dtype=object),
            "tokens": np.array(tokens, dtype=object),
            "logprobs": np.array(logprobs, dtype=np.float)
        }


    @batch
    def get_activations(self, request):
        """Retrieve intermediate activations from Falcon model"""
        response = self.generate(request)
        response["activations"] = torch.empty(0)
        response["error"] = "Activation retrival not implemented for Falcon model."
        return response


    @batch
    def edit_activations(self, request):
        """Edit intermediate activations from Falcon model"""
        response = self.generate(request)
        response["activations"] = torch.empty(0)
        response["error"] = "Activation editing not implemented for Falcon model."
        return response
