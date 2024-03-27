from langchain_community.llms import Ollama

ollama = Ollama(base_url='http://192.168.68.40:11434', model="llama2")
print(ollama.invoke("why is the sky blue"))
