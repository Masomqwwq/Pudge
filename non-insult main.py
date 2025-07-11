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
from random import randrange

# === Bot Setup ===
CHANNEL_ID = 709967557406490664  # Replace with your channel ID
intents = discord.Intents.default()
bot = commands.Bot(intents=intents)
load_dotenv()

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

def random_status(match, steamid):
    player = next((p for p in match['players'] if p.get("account_id") == int(steamid)), None)
    hero_id = player.get("hero_id", "unknown")
    hero_name = HERO_ID_MAP.get(hero_id, f"{hero_id}")
    kills = player.get("kills", 0)
    deaths = player.get("deaths", 0)
    assists = player.get("assists", 0)
    scoreline = kills + "/" + deaths + "/" + assists
    status = ["has made the ill-advised decision to play yet another game of DOTA 2.",
                "has decided that he hates himself enough to hit the queue button.",
                f"has decided that playing a game of {hero_name}.",
                "thought a game of dota would would curtail the pain.",
                "you get the idea, match details attached.",
                "has engaged in some truly fatherless activity",
                f"really? {hero_name}? okay pal.",
                "had a \"great\" time palying a match of Dota 2 yet again.",
                "has not learned their lesson after their last game.",
                "needs mental help, queued for Dota instead.",
                "needs to touch grass.",
                "is not him.",
                "go to bed.",
                f"is a(n) {hero_name} enjoyer now... I guess.",
                "had nothing better to do with their day.",
                "is playing dota 2 instead of cleaning their crusty ass room",
                "take a bath. Stinky.",
                "needs to think about the life decisions they have made that caused them to play this game.",
                "played ANOTHER game of DOTA 2.",
                "honestly I'm speechless.",
                "ew.",
                "what did you expect?",
                "\n I would have itemized differnetly but you do you bud.",
                "I guess this is better than League of Legends.",
                "this is what happens when you say \"one more\"",
                "you can't see it but the enemy team was calling you racial slurs in team chat.",
                "bg",
                "ggez",
                "did you buy that account? Looks like you bought that account.",
                "might need to ask Mason who he pays for MMR botting.",
                f"went {scoreline}",
                "needs to be put on a watchlist after that game.",
                "\n Teemo players ahve less crusty chairs than you after that game.",
                "maybe League ARAMS would be better after that match.",
                f"she dota on my {hero_name} till I {scoreline}",
                "Suicide Prevention Hotline: 1-(800)-273-8255.",
                "should try hots.",
                "is on a roll.",
                "is on fire.",
                f"I knew I never liked this guy, playing {hero_name} and shit.",
                "you might win mmr, but you will always lose braincells.",
                "clean up your desk before you queue again please.",
                "posture check.",
                "maybe marvel rivals next time?",
                "does anyone else have a boner right now? just me?",
                "don't forget to hydrate. You look like you need it.",
                "someone loves you. Not me, but someone. Probably.",
                "I'm starting to run out of funny things to say so have this family guy clip instead. \n https://www.youtube.com/shorts/eQdI5LScTHI",
                "what does dota have that I don't?",
                "@295326153462513665, I love you.",
                "@243565583629680641, tell this stink ass it's bed time.",
                "@247338225432002560 changed his name again",
                "MOOOOM, Phineas and Ferb are playing Dota 2 again.",
                "see I TOLD you this would happen.",
                "when will you learn? WHEN WILL YOU LEARN? THAT YOUR ACTIONS HAVE CONSEQUENCES?",
                "this would be a great opprotunity to get some sleep instead of queuing again.",
                "this is a test prompt, if you can see this something has gone horribly wrong, please contact @202173514004955136 and ask him to fix it.",
                "whens the last time you called your loved ones?",
                "considering you could be addicted to opiods, this isn't too bad?"
              ]
    return status[randrange(0, len(status)-1)]


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

                # Notify in Discord
                await channel.send(
                    f"<@{discord_id}> "
                    f"{random_status(match_details, steam_id)}\n"
                    f"[Link](<https://www.opendota.com/matches/{match_id}>)"
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
