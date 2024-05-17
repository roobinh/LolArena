import time
import requests
from riotwatcher import LolWatcher, ApiError

# Replace with your own API key
api_key = 'RGAPI-70b5e4f5-9c38-41f9-ab56-8a386a0c25d2'
region = 'europe'
lol_watcher = LolWatcher(api_key)
arena_god_challenge_id = 602002

# Define the Riot Account information
riot_id = 'tehruubin'
tagline = 'euw'
rate_limited = False

# Function to make API requests with rate limiting and retry on 429
def make_request(url, headers):
    global rate_limited

    while True:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            if rate_limited:
                print("No longer rate limited")
                rate_limited = False
            return response.json()
        elif response.status_code == 403:
            print('Forbidden: Check your API key and permissions.')
            return None
        elif response.status_code == 404:
            print('Resource not found.')
            return None
        elif response.status_code == 429:
            if not rate_limited:
                print(f'Rate limit response ({response.status_code}). Awaiting ')
                rate_limited = True
            time.sleep(10)
            return make_request(url, headers)
        else:
            print(f"Error: {response.status_code} - {response.json()}")
            return None

# Function to get PUUID using Riot ID and tagline
def get_puuid(api_key, riot_id, tagline):
    url = f'https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{riot_id}/{tagline}'
    headers = {
        'X-Riot-Token': api_key
    }
    return make_request(url, headers).get('puuid')

def get_champion_wins(api_key, puuid):
    champions_won = set()
    start = 0
    count = 10  # count per request
    arena_start_date = 1714521600000
    current_last_game = arena_start_date + 1

    while current_last_game > arena_start_date:
        print(f"{current_last_game} > {arena_start_date}")
        match_url = f'https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start={start}&count={count}'
        print(f'fetching match details: start={start}, count={count}')
        headers = {
            'X-Riot-Token': api_key
        }

        match_ids = make_request(match_url, headers)
        if not match_ids:
            break

        for match_id in match_ids:
            match_details = get_match_details(api_key, match_id)
            if match_details:
                if match_details.get('info').get('gameMode') == "CHERRY":
                    participants = match_details['info']['participants']
                    for participant in participants:
                        if participant['puuid'] == puuid:
                            if participant['placement'] == 1:
                                champions_won.add(participant['championName'])
            current_last_game = match_details.get('info').get('gameCreation')
            print(f"match_id={match_id}, game timestamp = {current_last_game}")
                                
        start += count

    print(f"Total matches: {len(match_ids)}")
    return champions_won

# Function to get match details
def get_match_details(api_key, match_id):
    match_url = f'https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}'
    headers = {
        'X-Riot-Token': api_key
    }
    return make_request(match_url, headers)

# Fetch the PUUID
puuid = get_puuid(api_key, riot_id, tagline)
if puuid:
    champions_wins = get_champion_wins(api_key, puuid)
    print(f"Champions wins for challenge Arena God:")
    for champ in champions_wins:
        print(champ)
else:
    print("Summoner with name and tagline does't exist")