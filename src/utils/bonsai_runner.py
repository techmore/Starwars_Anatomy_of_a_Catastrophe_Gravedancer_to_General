"""JSON-lines bridge executed by the isolated Bonsai MLX runtime.

This module deliberately imports only the alternate runtime's dependencies.
The Streamlit process retains its existing MLX environment, while 1-bit Bonsai
loads through Prism's MLX fork in a separate Python 3.11 virtual environment.
"""

import json
import sys


def _chat_prompt(tokenizer, prompt: str, system: str | None) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        return tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, enable_thinking=False
        )
    except TypeError:
        return tokenizer.apply_chat_template(messages, add_generation_prompt=True)


def main() -> None:
    request = json.loads(sys.stdin.readline())
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import (
        make_frequency_penalty,
        make_repetition_penalty,
        make_sampler,
    )

    model, tokenizer = load(request["model"])
    formatted_prompt = _chat_prompt(tokenizer, request["prompt"], request.get("system"))
    sampler = make_sampler(temp=request["temperature"], top_p=request["top_p"])
    logits_processors = [
        make_repetition_penalty(
            request.get("repetition_penalty", 1.08),
            request.get("repetition_context", 256),
        ),
        make_frequency_penalty(request.get("frequency_penalty", 0.04), 256),
    ]
    emitted = ""
    for response in stream_generate(
        model, tokenizer, formatted_prompt,
        max_tokens=request["max_tokens"], sampler=sampler,
        logits_processors=logits_processors,
    ):
        text = response.text
        delta = text[len(emitted):] if text.startswith(emitted) else text
        emitted = text
        if delta:
            print(json.dumps({"type": "delta", "text": delta}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"type": "error", "message": str(error)}), flush=True)
        raise
