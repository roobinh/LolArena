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

# Function to get PUUID using Riot ID and tagline
def get_puuid(api_key, riot_id, tagline, region):
    url = account_endpoint.format(region=region, gameName=riot_id, tagLine=tagline)
    headers = {
        'X-Riot-Token': api_key
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('puuid')
    elif response.status_code == 403:
        print('Forbidden: Check your API key and permissions.')
    elif response.status_code == 429:
        print('Rate limited. Try again later.')
    elif response.status_code == 404:
        print('Summoner with that Riot ID and tagline not found.')
    else:
        print(f"Error: {response.status_code} - {response.json()}")
    return None

# Function to get match history
def get_match_history(api_key, region, puuid, count=20):
    match_url = f'https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?count={count}'
    headers = {
        'X-Riot-Token': api_key
    }
    response = requests.get(match_url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching match history: {response.status_code} - {response.json()}")
        return None

# Function to get match details
def get_match_details(api_key, region, match_id):
    match_url = f'https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}'
    headers = {
        'X-Riot-Token': api_key
    }
    response = requests.get(match_url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching match details: {response.status_code} - {response.json()}")
        return None

# Fetch the PUUID
puuid = get_puuid(api_key, riot_id, tagline, 'europe')
if puuid:
    print(f"PUUID: {puuid}")
    games_amount = 100
    # Fetch match history
    match_history = get_match_history(api_key, 'europe', puuid, count=games_amount)
    
    if match_history:
        champions_won = set()
        
        for match_id in match_history:
            match_details = get_match_details(api_key, 'europe', match_id)
            if match_details:
                if match_details.get('info').get( 'gameMode') == "CHERRY":
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
