import os
import random
import requests

bot_token = os.environ.get("BOT_TOKEN")
chat_id = os.environ.get("CHAT_ID")

templates = [
    "🎉 የዛሬው የህዳሴ ዲጂታል ሎተሪ እድለኛ ቁጥሮች ወጥተዋል! አሁኑኑ እድልዎን ይሞክሩ።",
    "✨ ዛሬ የእርስዎ እድለኛ ቀን ሊሆን ይችላል! በህዳሴ ዲጂታል ሎተሪ ተሳታፊ ይሁኑ።",
    "🚀 የዛሬውን የሎተሪ እድል እንዳያመልጥዎት! አሁኑኑ ቲኬትዎን ይቁረጡ።"
]

message = random.choice(templates)

url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
payload = {
    "chat_id": chat_id,
    "text": message
}

response = requests.post(url, json=payload)
print(response.json())
