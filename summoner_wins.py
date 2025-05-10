import aiohttp
import asyncio
import os, json
import time
import discord
from riotwatcher import LolWatcher, ApiError

# Helper function to load or initialize the wins data
def load_arena_games():
    if os.path.exists(GAMES_FILENAME):
        try:
            with open(GAMES_FILENAME, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return {}
    return {}

# Helper function to save the wins data
def save_arena_games(data):
    with open(GAMES_FILENAME, "w") as file:
        json.dump(data, file, indent=4)

GAMES_FILENAME = "arena_games.json"

class CustomRiotAPI:
    def __init__(self, api_key, region='europe'):
        self.api_key = api_key
        self.region = region
        self.lol_watcher = LolWatcher(api_key)
        self.arena_god_challenge_id = 602002
        self.rate_limited = False
        self.session = aiohttp.ClientSession()  # Initialize the session
        

    async def make_request(self, url, headers, retry=0):
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        if self.rate_limited:
                            # print("No longer rate limited")
                            self.rate_limited = False
                        return await response.json()
                    elif response.status == 403:
                        # print('Forbidden: Check your API key and permissions.')
                        return None
                    elif response.status == 404:
                        # print('Resource not found.')
                        return None
                    elif response.status == 429:
                        if not self.rate_limited:
                            # print(f"Rate limit response ({response.status}). Awaiting")
                            self.rate_limited = True
                        await asyncio.sleep(10)
                        return await self.make_request(url, headers)
                    else:
                        response_data = await response.json()
                        print(f"Error: {response.status} - {response_data}")
                        if retry > 3:
                            return None
                        return await self.make_request(url, headers, retry+1)

    async def is_api_token_valid(self, riot_id, tagline):
        url = f'https://{self.region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{riot_id}/{tagline}'
        headers = {'X-Riot-Token': self.api_key}
        response = await self.make_request(url, headers)
        return True if response is not None else False
    
    async def get_puuid(self, riot_id, tagline):
        url = f'https://{self.region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{riot_id}/{tagline}'
        headers = {'X-Riot-Token': self.api_key}
        account_response = await self.make_request(url, headers)
        return account_response.get('puuid') if account_response else None

    async def get_stats(self, participant):
        return {
            "total_damage": participant['totalDamageDealtToChampions'],
            "total_kills": participant['kills'],
            "total_deaths": participant['deaths'],
            "total_assists": participant['assists'],
            "total_heal" : participant['totalHeal'],
            "total_self_healing": participant['totalHeal'],
            "total__healing_on_allies": participant['totalHealsOnTeammates'],
            "total_shielding": participant['totalHealsOnTeammates'],
            "total_shielding_on_teammate": participant['totalDamageShieldedOnTeammates'],
            "physical_damage_taken": participant['physicalDamageTaken'],
            "cc_duration": participant['totalTimeCCDealt'],
            "highest_crit": participant['largestCriticalStrike'],
            "ability_1_used": participant['spell1Casts'],
            "ability_2_used": participant['spell2Casts'],
            "ability_3_used": participant['spell3Casts'],
            "ability_4_used": participant['spell4Casts'],
            "playerAugment1": participant['playerAugment1'],
            "playerAugment2": participant['playerAugment2'],
            "playerAugment3": participant['playerAugment3'],
            "gold_earned": participant['goldEarned'],
            "largestKillingSpree": participant['largestKillingSpree']
        }
        
    async def update_arena_games(self, interaction: discord.Interaction, user_key, user_name, puuid, lol_champions, latest_update=None, summoner_name=None, tagline=None):
        def get_teammate_info(match_details, team_id, puuuid_owner):
            participants = match_details['info']['participants']
            for participant in participants:
                if participant['playerSubteamId'] == team_id and participant['puuid'] != puuuid_owner:
                    teammate_name = participant['riotIdGameName']
                    normalized_champion_name = normalize_name(participant['championName'])
                    teammate_champion = next(
                        (champion for champion in lol_champions if normalize_name(champion) == normalized_champion_name),
                        participant['championName']
                    )
                    return teammate_name, teammate_champion
            return "Unknown", "Unknown"

        def normalize_name(name):
            return name.lower().replace("'", "").replace(" ", "")

        matches = []
        start = 0
        count = 10  # count per request
        
        arena_start_date = latest_update or 1740787261000  # 1 May 2024, Release date Arena (God Title)
        current_last_game = arena_start_date + 1
        
        while current_last_game > arena_start_date:
            match_url = f'https://{self.region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start={start}&count={count}'
            headers = {'X-Riot-Token': self.api_key}
            match_ids = await self.make_request(match_url, headers)
            if not match_ids:
                break

            for match_id in match_ids:
                match_details = await self.get_match_details(match_id)
                if match_details:
                    game_creation = match_details['info'].get('gameCreation')
                    if match_details.get('info').get('gameMode') == "CHERRY":
                        stats = {}
                    
                        participants = match_details['info']['participants']
                        for participant in participants:
                            if participant['puuid'] == puuid:
                                placement = participant['placement']
                                team_id = participant['playerSubteamId']
                                stats = await self.get_stats(participant)
                                normalized_champion_name = normalize_name(participant['championName'])
                                champion_name = next(
                                    (champion for champion in lol_champions if normalize_name(champion) == normalized_champion_name),
                                    participant['championName']
                                )
                        teammate_name, teammate_champion = get_teammate_info(match_details, team_id, puuid)
                        matches.append({
                            match_id: {
                                "champion": champion_name,
                                "teammate_name": teammate_name,
                                "teammate_champion": teammate_champion,
                                "timestamp": game_creation,
                                "place": placement,
                                "stats": stats
                            }
                        })                    
                    current_last_game = game_creation

            start += count
            
        await self.session.close() # Close connections
        arena_games = load_arena_games()

        if user_key not in arena_games:
            arena_games[user_key] = {"name": user_name, "summoner_name": summoner_name, "summoner_tagline": tagline, "arena_games": {}}
        
        if "arena_games" not in arena_games[user_key]:
            arena_games[user_key]["arena_games"] = {}

        for match in matches:
            for match_id, match_details in match.items():
                arena_games.get(user_key).get('arena_games')[match_id] = match_details
        arena_games[user_key]['latest_update'] = int(time.time()) * 1000
        save_arena_games(arena_games)
        return
    
    async def get_match_details(self, match_id):
        match_url = f'https://{self.region}.api.riotgames.com/lol/match/v5/matches/{match_id}'
        headers = {'X-Riot-Token': self.api_key}
        return await self.make_request(match_url, headers)
