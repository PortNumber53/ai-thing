import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("stabilityai/stable-code-instruct-3b", trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained("stabilityai/stable-code-instruct-3b", torch_dtype=torch.bfloat16, trust_remote_code=True)
model.eval()
# model = model.cuda('cpu')

messages = [
    {
        "role": "system",
        "content": "You are a helpful and polite assistant. You always reply using JSON format, the words in CAPITAL must be used for the keys in the JSON response.",
    },
    {
        "role": "user",
        "content": "Write a simple website in HTML. When a user clicks the button, it shows a random joke from a list of 4 jokes. Add an EXPLANATION of the CODE, and a suggestion on how to create a UNIT_TEST file."
    },
]

prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)

inputs = tokenizer([prompt], return_tensors="pt").to(model.device)

tokens = model.generate(
    **inputs,
    max_new_tokens=1024,
    temperature=0.5,
    top_p=0.95,
    top_k=100,
    do_sample=True,
    use_cache=True
)

output = tokenizer.batch_decode(tokens[:, inputs.input_ids.shape[-1]:], skip_special_tokens=False)[0]

print(output)
