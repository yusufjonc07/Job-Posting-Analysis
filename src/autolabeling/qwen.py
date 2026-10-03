import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_NAME = "Qwen/Qwen3-1.7B"

# Device
if torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"

print(f"Using device: {device}")
print(f"MPS available: {torch.backends.mps.is_available()}")
print(f"PyTorch version: {torch.__version__}")

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

# Load model
print("Loading model...")

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    dtype=torch.float16,
)

model.to(device)
model.eval()

print("Model loaded successfully.")

 # Example Uzbek job posting
job_text = """
There is work available in Icheon from Monday to Friday. Schedule: Monday 18:50–06:40; Tuesday through Friday 19:30–06:40. Wages are paid daily. Address: 57 Choji-ri, Daewol-myeon, Icheon-si, Gyeonggi-do.
"""
prompt = f"""
Is that job posting ? (Answer Yes/No, no other any word)

Job posting:
{job_text}
"""


inputs = tokenizer(
    prompt,
    return_tensors="pt"
).to(device)

print("Generating...")

with torch.inference_mode():
    outputs = model.generate(
        **inputs,
        max_new_tokens=50,
        do_sample=False,
    )

# Remove input tokens
generated_tokens = outputs[0][inputs["input_ids"].shape[1]:]

answer = tokenizer.decode(
    generated_tokens,
    skip_special_tokens=True,
)

print("\nAnswer:")
print(answer)