import discord
from discord.ext import commands, tasks
import asyncio
import aiohttp
import csv
import os
import json
from groq import Groq
import requests
from datetime import datetime
from dotenv import load_dotenv

# === Bot Setup ===
CHANNEL_ID = 663995718624870400  # Replace with your channel ID
intents = discord.Intents.default()
bot = commands.Bot(intents=intents)
load_dotenv()
groq_client = Groq(api_key=os.environ["GROQ_KEY"])


# Load items.json and create ITEM_ID_MAP
item_response = requests.get("https://raw.githubusercontent.com/odota/dotaconstants/master/build/items.json")
items_data = item_response.json()
ITEM_ID_MAP = {item_info['id']: name for name, item_info in items_data.items()}

# Load hero_names.json and create HERO_ID_MAP
hero_response = requests.get("https://raw.githubusercontent.com/odota/dotaconstants/master/build/heroes.json")
if hero_response.status_code != 200:
    print("Error fetching hero names:", hero_response.text)
    exit(1)  # Or handle gracefully
try:
    heroes_data = hero_response.json()
except Exception as e:
    print("Error parsing heroes JSON:", hero_response.text)
    raise e

HERO_ID_MAP = {hero['id']: hero['localized_name'] for hero in heroes_data.values()}

# === File Paths ===
TARGETS_CSV = "targets.csv"
MATCH_HISTORY_DIR = "Match History"
LAST_MATCHES_FILE = "last_matches.json"

# === Generate Insult ===
def generate_insult(match_data: dict) -> str:
    player = match_data['players'][0]

    kills = player.get("kills", 0)
    deaths = player.get("deaths", 0)
    assists = player.get("assists", 0)
    hero_id = player.get("hero_id", "unknown")
    hero_name = get_hero_name(hero_id)
    gpm = player.get("gold_per_min", 0)
    xpm = player.get("xp_per_min", 0)
    last_hits = player.get("last_hits", 0)
    lh_t = player.get("lh_t", [])
    lh_at_10 = lh_t[10] if len(lh_t) > 10 else "N/A"

    # Item slots and timings
    items = []
    for i in range(6):
        item_key = f"item_{i}"
        item_id = player.get(item_key)
        if item_id and item_id != 0:
            item_name = get_item_name(item_id)
            purchase_log = next((log for log in player.get("purchase_log", []) if log["key"] == item_name), None)
            time = purchase_log["time"] if purchase_log else None
            if time is not None:
                minutes = round(time / 60)
                items.append(f"{item_name} @ {minutes}min")
            else:
                items.append(item_name)

    item_list = ', '.join(items) if items else "No items?"

    # LLM Prompt
    prompt = f"""
    Here is my friend's performance in a recent Dota 2 match:

    Hero: {hero_name}
    Kills/Deaths/Assists: {kills}/{deaths}/{assists}
    GPM: {gpm}
    XPM: {xpm}
    Last Hits: {last_hits} (LH@10: {lh_at_10})
    Items: {item_list}

    Let them know how bad at the game they are. Keep the insults creative and scathing, but not too long.
    """

    try:
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.95,
            max_tokens=120
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("Groq API error:", e)
        return "In case you needed a reminder of your ACTUAL MMR."


def get_item_name(item_id):
    return ITEM_ID_MAP.get(item_id, f"Item#{item_id}")

def get_hero_name(hero_id):
    return HERO_ID_MAP.get(hero_id, f"Hero#{hero_id}")

# === Load Targets ===
def load_targets():
    users = []
    with open(TARGETS_CSV, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            users.append({
                "discord_id": row["discord_id"],
                "steam_id": row["steam_id"]
            })
    return users


# === Match State Persistence ===
def load_last_matches():
    if os.path.exists(LAST_MATCHES_FILE):
        with open(LAST_MATCHES_FILE, "r") as f:
            return json.load(f)
    return {}


def save_last_matches(data):
    with open(LAST_MATCHES_FILE, "w") as f:
        json.dump(data, f, indent=2)


# === Background Task ===
@tasks.loop(minutes=3)
async def check_matches():
    print(f"[{datetime.now()}] Checking for new matches...")
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("Error: Could not find the Discord channel.")
        return

    last_matches = load_last_matches()
    users = load_targets()

    async with aiohttp.ClientSession() as session:
        for user in users:
            steam_id = user["steam_id"]
            discord_id = user["discord_id"]

            try:
                async with session.get(f"https://api.opendota.com/api/players/{steam_id}/recentMatches") as resp:
                    if resp.status != 200:
                        continue
                    matches = await resp.json()

                if not matches:
                    continue

                latest = matches[0]
                match_id = str(latest["match_id"])

                if last_matches.get(steam_id) == match_id:
                    continue  # Already seen

                # Fetch full match details
                async with session.get(f"https://api.opendota.com/api/matches/{match_id}") as resp:
                    if resp.status != 200:
                        continue
                    match_details = await resp.json()

                # Save match
                user_dir = os.path.join(MATCH_HISTORY_DIR, steam_id)
                os.makedirs(user_dir, exist_ok=True)
                match_path = os.path.join(user_dir, f"{match_id}.json")
                with open(match_path, "w") as f:
                    json.dump(match_details, f, indent=2)

                # Update seen match
                last_matches[steam_id] = match_id
                save_last_matches(last_matches)

                # Generate insult with LLM
                insult = generate_insult(match_details)

                # Notify in Discord
                await channel.send(
                    f"<@{discord_id}>\n"
                    f"{insult}\n"
                    f"[Link](https://www.opendota.com/matches/{match_id})"
                )

                await asyncio.sleep(1)  # avoid rate limits

            except Exception as e:
                print(f"Error checking user {steam_id}: {e}")
    print("done")


# === Bot Events ===
@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    check_matches.start()


bot.run(os.environ["DISCORD_TOKEN"])
