import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("EVENTS_PROVIDER_API_KEY")

if not key:
    print("❌ Ключ не найден в .env!")
else:
    parts = key.split(".")
    print(f"✅ Ключ найден. Длина: {len(key)} символов")
    print(f"🧩 Сегментов (по точкам): {len(parts)}")
    if len(parts) == 3:
        print("🎉 Формат JWT выглядит корректным!")
    else:
        print("💥 Ошибка: JWT должен состоять из 3 сегментов (header.payload.signature).")
        print("   Сейчас у тебя:", parts)
