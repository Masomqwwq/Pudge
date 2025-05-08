import requests
import datetime
import os
import json
import csv

def load_users(csv_path):
    users = []
    with open(csv_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            users.append({
                "discord_id": row["discord_id"],
                "steam_id": row["steam_id"]
            })
    return users

# Example use
users = load_users("targets.csv")

# Get all Steam IDs
steam_ids = [user["steam_id"] for user in users]

def fetch_and_save_latest_match(account_id):
    # 1. Get recent matches from OpenDota
    response = requests.get(f"https://api.opendota.com/api/players/{account_id}/recentMatches")

    if not response.ok:
        print(f"[{datetime.datetime.now()}] Failed to fetch recent matches for {account_id}")
        return

    matches = response.json()
    if not matches:
        print(f"[{datetime.datetime.now()}] No matches found for {account_id}")
        return

    # 2. Get most recent match ID
    latest_match = matches[0]
    match_id = str(latest_match["match_id"])
    user_id = str(account_id)

    # 3. Check if file already exists
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Match History", user_id))
    os.makedirs(base_path, exist_ok=True)
    file_path = os.path.join(base_path, f"{match_id}.json")

    if os.path.exists(file_path):
        print(f"[{datetime.datetime.now()}] Match {match_id} for {user_id} already exists.")
        return

    # 4. Fetch match details
    detail_response = requests.get(f"https://api.opendota.com/api/matches/{match_id}")
    if not detail_response.ok:
        print(f"[{datetime.datetime.now()}] Failed to fetch match {match_id} for {user_id}")
        return

    match_details = detail_response.json()

    # 5. Save match data
    with open(file_path, "w") as f:
        json.dump(match_details, f, indent=2)

    print(f"[{datetime.datetime.now()}] Saved match {match_id} for user {user_id}.")

def main():
    for uid in steam_ids:
        fetch_and_save_latest_match(uid)
    print("done")

if __name__ == "__main__":
    main()