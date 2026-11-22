import httpx


async def translate_to_english(text: str, url: str, api_key: str = "") -> str:
    payload = {
        "q": text,
        "source": "auto",
        "target": "en",
        "format": "text",
    }
    if api_key:
        payload["api_key"] = api_key

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    translated = data.get("translatedText")
    if not translated:
        raise RuntimeError("Сервіс перекладу не повернув текст")
    return translated
