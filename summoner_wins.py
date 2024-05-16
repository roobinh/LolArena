import time
import requests
from riotwatcher import LolWatcher, ApiError

# Replace with your own API key
api_key = 'RGAPI-dcdaa92f-96fc-4720-b177-99988a57eb9e'
lol_watcher = LolWatcher(api_key)

# Set the region and account endpoint
my_region = 'euw1'  # Platform routing value for EUW
account_endpoint = 'https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}'

# Define the Riot ID and tagline
riot_id = 'tehruubin'
tagline = 'euw'
arena_god_challenge_id = 602002

# Set rate limits
rate_limit = 100 # Max 100 Requests...
rate_limit_time = 120 # ... per 120 seconds

# Function to check and handle rate limit
def check_rate_limit(request_counter):
    print(f"request_counter = {request_counter}")
    if request_counter['count'] >= rate_limit:
        print("Rate limit reached. Sleeping for 2 minutes...")
        time.sleep(rate_limit_time)
        request_counter['count'] = 0

# Function to make API requests with rate limiting and retry on 429
def make_request(url, headers, request_counter):
    while True:
        check_rate_limit(request_counter)
        response = requests.get(url, headers=headers)
        request_counter['count'] += 1
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            print('Forbidden: Check your API key and permissions.')
            return None
        elif response.status_code == 429:
            print('Rate limited. Sleeping for 2 minutes...')
            time.sleep(rate_limit_time)
            request_counter['count'] = 0
        elif response.status_code == 404:
            print('Resource not found.')
            return None
        else:
            print(f"Error: {response.status_code} - {response.json()}")
            return None

# Function to get PUUID using Riot ID and tagline
def get_puuid(api_key, riot_id, tagline, region, request_counter):
    url = account_endpoint.format(region=region, gameName=riot_id, tagLine=tagline)
    headers = {
        'X-Riot-Token': api_key
    }
    return make_request(url, headers, request_counter).get('puuid')

# Function to get match history
def get_match_history(api_key, region, puuid, count, request_counter):
    match_url = f'https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?count={count}'
    headers = {
        'X-Riot-Token': api_key
    }
    return make_request(match_url, headers, request_counter)

# Function to get match details
def get_match_details(api_key, region, match_id, request_counter):
    match_url = f'https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}'
    headers = {
        'X-Riot-Token': api_key
    }
    return make_request(match_url, headers, request_counter)

# Initialize request counter
request_counter = {'count': 0}

# Fetch the PUUID
puuid = get_puuid(api_key, riot_id, tagline, 'europe', request_counter)
if puuid:
    print(f"PUUID: {puuid}")
    games_amount = 500
    # Fetch match history
    match_history = get_match_history(api_key, 'europe', puuid, count=games_amount, request_counter=request_counter)
    
    if match_history:
        champions_won = set()
        
        for match_id in match_history:
            match_details = get_match_details(api_key, 'europe', match_id, request_counter=request_counter)
            if match_details:
                if match_details.get('info').get('gameMode') == "CHERRY":
                    participants = match_details['info']['participants']
                    for participant in participants:
                        if participant['puuid'] == puuid:
                            if participant['placement'] == 1:
                                champions_won.add(participant['championName'])
        
        print(f"Champions won for challenge Arena God (last {games_amount} games):")
        for champ in champions_won:
            print(champ)
else:
    print("Failed to retrieve PUUID. Exiting...")

# Debug information
print("------- Debug Information: --------")
print(f"API Key: {api_key[:5]}...{api_key[-5:]} (masked for security)")
print(f"Account Endpoint URL: {account_endpoint.format(region='europe', gameName=riot_id, tagLine=tagline)}")
print(f"Region: {my_region}")
