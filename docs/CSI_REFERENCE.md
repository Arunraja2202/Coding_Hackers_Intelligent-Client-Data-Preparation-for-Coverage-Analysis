# CSI reference

This project was wired from the supplied CSI notebook `test(5).ipynb`.

Reference integration details used:

```text
endpoint = https://llm-api-cis.azure-intlsd-np.nielsencsp.net/
api_version = 2025-03-01-preview
model = hack-fest-gpt-5.6-luna
client = ChatCompletionsClient(..., credential=AzureKeyCredential(api_key), ...)
headers = {"Authorization": api_key}
```

The application does not hard-code the secret. Set `CSI_LLM_API_KEY` in `.env`.
