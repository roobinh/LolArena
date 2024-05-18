import aiohttp
import asyncio
from riotwatcher import LolWatcher, ApiError

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
                        return self.make_request(url, headers)
                    else:
                        response_data = await response.json()
                        print(f"Error: {response.status} - {response_data}")
                        if retry > 3:
                            return None
                        return self.make_request(url, headers, retry+1)

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

    async def get_champion_wins(self, puuid, latest_update=None):
        champions_won = {}
        start = 0
        count = 10  # count per request
        arena_start_date = latest_update or 1714521600000 # 1 May 2024, Release date Arena (God Title)
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
                    if match_details.get('info').get('gameMode') == "CHERRY":
                        participants = match_details['info']['participants']
                        for participant in participants:
                            if participant['puuid'] == puuid and participant['placement'] == 1:
                                champion_name = participant['championName']
                                game_creation = match_details.get('info').get('gameCreation')
                                # Update the dictionary only if the champion's win date is later than the stored one
                                if champion_name not in champions_won or game_creation > champions_won[champion_name]:
                                    champions_won[champion_name] = game_creation
                    current_last_game = match_details.get('info').get('gameCreation')

            start += count
        return champions_won


    async def get_match_details(self, match_id):
        match_url = f'https://{self.region}.api.riotgames.com/lol/match/v5/matches/{match_id}'
        headers = {'X-Riot-Token': self.api_key}
        return await self.make_request(match_url, headers)

    async def close_session(self):
        await self.session.close()  # Remember to close the session when done
