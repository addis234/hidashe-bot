import os
import random
import requests

TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# 1. የሽልማቱ ዝርዝር
PRIZE_LIST = """
🎁 የሽልማት ዝርዝር፦
1️⃣ 1ኛ እጣ፦ 10,000 ብር  
2️⃣ 2ኛ እጣ፦ 8,000 ብር  
3️⃣ 3ኛ እጣ፦ 6,000 ብር  
4️⃣ 4ኛ እጣ፦ 5,000 ብር  
5️⃣ 5ኛ እጣ፦ 4,000 ብር  
6️⃣ 6ኛ እጣ፦ 3,000 ብር  
7️⃣ 7ኛ እጣ፦ 2,000 ብር  
8️⃣ 8ኛ እጣ፦ 1,500 ብር  
9️⃣ 9ኛ እጣ፦ 1,000 ብር  
🔟 10ኛ እጣ፦ 500 ብር  

✨ ሌሎች አጓጊ ሽልማቶችን በሁለተኛ ዙር ይጠብቁን!
"""

# 2. የተለያዩ አነሳሽ የመግቢያና የመውጫ መልእክቶች (Prompts/Templates)
TEMPLATES = [
    # Template 1
    """🎰 የህዳሴ ዲጂታል ሎተሪ 🎰

አሁኑኑ ይሳተፉ! የእድሉ ባለቤት ይሁኑ!

{prizes}

📲 ለማሸነፍና ለመሳተፍ አሁኑኑ ይመዝገቡ!""",
    # Template 2
    """🔥 የዛሬው የእድልዎ ቀን ሊሆን ይችላል! 🔥

በትንሽ ተሳትፎ ትልቅ የገንዘብ ሽልማቶችን ያሸንፉ! 💰

{prizes}

👉 ዕድልዎን አሁኑኑ ይሞክሩ!""",
    # Template 3
    """✨ ህልምዎን እውን የሚያደርጉበት መልካም አጋጣሚ! ✨

በህዳሴ ዲጂታል ሎተሪ ይሳተፉ፤ አሸናፊ ይሁኑ! 🎉

{prizes}

🚀 አሁኑኑ በመመዝገብ ተሳትፎዎን ያረጋግጡ!""",
    # Template 4
    """🌟 ለውጥ በአንድ እርምጃ ይጀምራል! 🌟

የዛሬው ዕድለኛ እርስዎ ይሆኑ ይሆን? ይሳተፉ፣ ያሸንፉ!

{prizes}

መልካም ዕድል ለሁላችሁም! 🍀""",
]


def send_random_advertisement():
    # ከቡድኑ ውስጥ አንዱን መልእክት በዘፈቀደ መምረጥ
    selected_template = random.choice(TEMPLATES)
    full_message = selected_template.format(prizes=PRIZE_LIST)

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": full_message}

    response = requests.post(url, data=payload)
    print(response.json())


if __name__ == "__main__":
    send_random_advertisement()
