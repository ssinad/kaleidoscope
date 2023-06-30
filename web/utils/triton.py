from flask import current_app
import numpy as np
import tritonclient.http as httpclient
from tritonclient.utils import np_to_triton_dtype, triton_to_np_dtype
import typing
import ast


def _param(dtype, value, batch_size):
    if bool(value):
        return np.ones((batch_size, 1), dtype=dtype) * value
    else:
        return np.zeros((batch_size, 1), dtype=dtype) + value

def _str_list2numpy(str_list: typing.List[str]) -> np.ndarray:
    str_ndarray = np.array(str_list)
    return np.char.encode(str_ndarray, "utf-8")

def prepare_prompts_tensor(prompts):
    name, value =  "prompts", prompts

    triton_dtype = "BYTES"
    input = _str_list2numpy(value)
    # np.array(value, dtype=bytes)

    tensor = httpclient.InferInput(name, input.shape, triton_dtype)
    tensor.set_data_from_numpy(input)
    return tensor

def prepare_param_tensor(input, inputs_config, batch_size):
    current_app.logger.info(f"Preparing param tensor, input={input}, inputs_config={inputs_config}, batch_size={batch_size}")
    name, value = input
    current_app.logger.info(f"Preparing param tensor, name={name}, value={value}")
    input_config = [input_config for input_config in inputs_config if input_config['name'] == name][0]
    current_app.logger.info(f"Preparing param tensor, input_config={input_config}")
    triton_dtype = input_config['data_type'].split('_')[1]
    if triton_dtype == "STRING":
        triton_dtype = "BYTES"
        value = _str_list2numpy(value)
    input = _param(triton_to_np_dtype(triton_dtype), value, batch_size)

    tensor = httpclient.InferInput(name, input.shape, triton_dtype)
    tensor.set_data_from_numpy(input)
    return tensor

def prepare_inputs(inputs, inputs_config):
    """
    Prepare inputs for Triton
    """
    inputs = inputs.copy()
    prompts = [[prompt] for prompt in inputs['prompts']]
    batch_size = len(prompts)
    inputs.pop('prompts')

    inputs_wrapped = [prepare_prompts_tensor(prompts)]
    
    current_app.logger.info(f"Input args: {inputs}")
    for input in inputs.items():
        inputs_wrapped.append(prepare_param_tensor(input, inputs_config, batch_size))

    return inputs_wrapped


class TritonClient():

    def __init__(self, host):
        self._client = httpclient.InferenceServerClient(host, concurrency=1, verbose=True)

    def infer(self, model_name, inputs, task="generation"):
        model_bind_name = f'{model_name}_{task}'
        task_config = self._client.get_model_config(model_bind_name)

        inputs_wrapped = prepare_inputs(inputs, task_config['input'])

        response = self._client.infer(model_bind_name, inputs_wrapped)
        
        sequences = np.char.decode(response.as_numpy("sequences").astype("bytes"), "utf-8").tolist()
        tokens = np.char.decode(response.as_numpy("tokens").astype("bytes"), "utf-8").tolist()
        
        logprobs = np.char.decode(response.as_numpy("logprobs").astype("bytes"), "utf-8").tolist()
        for i in range(len(logprobs)):
            logprobs[i] = [float(prob) if prob!="None" else None for prob in logprobs[i]]

        result = {
            "sequences": sequences,
            "tokens": tokens,
            "logprobs": logprobs
        }
        
        if task == "activations":
            activations = np.char.decode(response.as_numpy("activations").astype("bytes"), "utf-8").tolist()
            for idx in range(len(activations)):
                activations[idx] = ast.literal_eval(activations[idx])
            result.update({"activations": activations})

        return result

    def is_model_ready(self, model_name, task="generation"):
        model_bind_name = f'{model_name}_{task}'
        print(model_bind_name)
        is_model_ready = self._client.is_model_ready(model_bind_name)
        return is_model_ready
