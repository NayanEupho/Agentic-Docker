import dspy
print("DSPy Version:", dspy.__version__)
print("\nAttributes in dspy:")
for attr in dir(dspy):
    if "ollama" in attr.lower():
        print(f" - {attr}")
    if "lm" in attr.lower():
        print(f" - {attr}")
        
try:
    from dspy.retrieve.ollama import OllamaLocal
    print("\nFound OllamaLocal in dspy.retrieve.ollama")
except ImportError:
    pass
