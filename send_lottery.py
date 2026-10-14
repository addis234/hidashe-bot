import os
import random
import requests

bot_token = os.environ.get("BOT_TOKEN")
chat_id = os.environ.get("CHAT_ID")

templates = [
    (
        "🎉 የህዳሴ ዲጂታል ሎተሪ - እድልዎን ይሞክሩ፣ ታላላቅ ሽልማቶችን ያሸንፉ! 🎉\n\n"
        "የሎተሪ ትኬት በመቁረጥ እንዲሁም ለጓደኞችዎ በማጋራት አጓጊ የገንዘብ ሽልማቶችን የሚያሸንፉበት ዘመናዊ የቴሌግራም ቦት! 🚀\n\n"
        "🎁 የመጀመሪያው ዙር የታላላቅ እጣዎች ዝርዝር፦\n"
        "🥇 1ኛ እጣ፦ 10,000 ብር\n"
        "🥈 2ኛ እጣ፦ 8,000 ብር\n"
        "🥉 3ኛ እጣ፦ 6,000 ብር\n"
        "🏅 4ኛ እጣ፦ 5,000 ብር\n"
        "🏅 5ኛ እጣ፦ 4,000 ብር\n"
        "🏅 6ኛ እጣ፦ 3,000 ብር\n"
        "🏅 7ኛ እጣ፦ 2,000 ብር\n"
        "🏅 8ኛ እጣ፦ 1,500 ብር\n"
        "🏅 9ኛ እጣ፦ 1,000 ብር\n"
        "🏅 10ኛ እጣ፦ 500 ብር\n\n"
        "✨ ተጨማሪ ልዩ እድል (ያለ ምንም ካፒታል ብር ይስሩ)!\n"
        "ቦቱን ለሌሎች ሲጋብዙ በየሰው 10 ETB ኮሚሽን በቀጥታ ወደ ዋሌትዎ ገቢ ይሆናል!\n\n"
        "📺 የሎተሪ እጣ አወጣጡ በቻናላችን ላይ በቀጥታ (Live) ግልጽ በሆነ መልኩ ይተላለፋል።\n\n"
        "👇 አሁኑኑ ትኬት ለመቁረጥ እና መሳተፍ ለመጀመር እዚህ ይጫኑ፦\n"
        "🔗 https://t.me/lottery_test_123_bot?start=6722504980"
    ),
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
