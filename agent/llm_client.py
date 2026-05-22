import os
import json
from config import ModelConfig


def call_llm(
    model_config: ModelConfig,
    system_prompt: str,
    user_message: str,
    tools: list,
    max_tokens: int = 2000,
) -> dict:
    """
    Unified LLM call supporting Anthropic and Groq.
    Tools must be in OpenAI function format:
      {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    Returns: {"name": tool_name, "input": dict}
    """
    if model_config.provider == "anthropic":
        return _call_anthropic(model_config.model_id, system_prompt, user_message, tools, max_tokens)
    elif model_config.provider == "groq":
        return _call_groq(model_config.model_id, system_prompt, user_message, tools, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {model_config.provider}")


def _call_anthropic(model_id, system_prompt, user_message, tools, max_tokens):
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    anthropic_tools = [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "input_schema": t["function"]["parameters"],
        }
        for t in tools
    ]

    response = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        system=system_prompt,
        tools=anthropic_tools,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    return {"name": tool_block.name, "input": tool_block.input}


def _call_groq(model_id, system_prompt, user_message, tools, max_tokens):
    import re
    from openai import OpenAI, BadRequestError

    client = OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
    )

    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            tools=tools,
            tool_choice="required",
        )

        tool_call = response.choices[0].message.tool_calls[0]
        return {
            "name": tool_call.function.name,
            "input": json.loads(tool_call.function.arguments),
        }

    except BadRequestError as e:
        # Groq/Llama occasionally emits <function=name>{...}</function> instead of
        # a proper tool call. The JSON inside is valid — parse it and recover.
        body = e.body or {}
        failed = body.get("error", {}).get("failed_generation", "")
        match = re.search(r"<function=(\w+)>(.*?)</function>", failed, re.DOTALL)
        if match:
            return {
                "name": match.group(1),
                "input": json.loads(match.group(2)),
            }
        raise
