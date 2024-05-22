import os, json, random, discord, subprocess, requests
import time
from typing import List
from dotenv import dotenv_values
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from summoner_wins import CustomRiotAPI

def load_champion_list(file_path="lol_champions.json"):
    with open(file_path, "r") as file:
        data = json.load(file)
    return data["champions"]

# Helper function to load or initialize the wins data
def load_arena_games():
    if os.path.exists(GAMES_FILENAME):
        try:
            with open(GAMES_FILENAME, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return {}
    return {}

# List of League of Legends champions
LOL_CHAMPIONS = load_champion_list()
GAMES_FILENAME = "arena_games.json"

# Get tokens
env = dotenv_values('.env')
BOT_TOKEN = env.get('BOT_TOKEN_DEV') or env.get('BOT_TOKEN')
GUILD_ID = env.get("GUILD_ID", None)
RIOT_API_TOKEN = env.get("RIOT_API_TOKEN", None)

# Bot Variables
intents = discord.Intents.all()
intents.voice_states = True
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
riot_api = CustomRiotAPI(RIOT_API_TOKEN)
last_reroll_time = time.time()

class TeamMemberSelectionView(discord.ui.View):
    def __init__(self, members):
        super().__init__()
        # Add a select menu with the members in the voice channel
        self.add_item(TeamMemberSelectMenu(members))


class TeamMemberSelectMenu(discord.ui.Select):
    def __init__(self, members):
        options = [
            discord.SelectOption(label=member.name, value=str(member.id)) for member in members 
        ]
        super().__init__(
            placeholder="Select members...",
            min_values=2,  # Minimum number of selections
            max_values=len(options),  # Maximum number of selections
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_members = [discord.utils.get(interaction.guild.members, id=int(member_id)) for member_id in self.values]
        selected_members = [member for member in selected_members if member is not None]  # Filter out None values

        random.shuffle(selected_members)
        teams = [selected_members[i:i + 2] for i in range(0, len(selected_members), 2)]
        if len(selected_members) % 2 == 1 and len(teams[-1]) == 2:
            teams[-1].append(teams[-1].pop().name)  # Move the last member as a name to the team

        embed = discord.Embed(
            title="Teams for Arena",
            description="\n".join([f"Team {i+1}: {', '.join([member.name for member in team])}" for i, team in enumerate(teams)]),
            color=discord.Color.green()
        )
        await interaction.response.edit_message(content="", embed=embed, view=None)


class AddChampionModal(Modal):
    def __init__(self, user_id, ctx):
        super().__init__(title="Add a Champion to Your Win List")
        self.user_id = user_id
        self.ctx = ctx
        self.champion_input = TextInput(label="Champion Name", placeholder="e.g., Ahri, Zed")
        self.add_item(self.champion_input)

    async def on_submit(self, interaction: discord.Interaction):
        entered_champion = self.champion_input.value.strip()
        entered_champion = next((champion for champion in LOL_CHAMPIONS if champion.lower() == entered_champion.lower()), entered_champion)

        if entered_champion not in LOL_CHAMPIONS:
            await interaction.response.send_message(f"Champion **{entered_champion}** not found in the available champion list.", ephemeral=True)
            return

        arena_games = load_arena_games()
        user_key = str(self.user_id)

        if user_key not in arena_games:
            arena_games[user_key] = {"name": interaction.user.name, "wins": []}
        elif "wins" not in arena_games[user_key]:
            arena_games[user_key]["wins"] = []

        existing_champions = [win["champion"] for win in arena_games[user_key]["wins"]]
        if entered_champion not in existing_champions:
            arena_games[user_key]["wins"].append({
                "champion": entered_champion,
                "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M")
            })
            save_arena_games(arena_games)
            
            # Fetch the new embed and view with the updated win list
            embed, view = await get_wins_embed_and_view(interaction, interaction.user)
            status_message = f"✅**{entered_champion}** has been successfully added to your win list."
            await interaction.response.edit_message(content=status_message, embed=embed, view=view)
        else:
            await interaction.response.send_message(content=f"**{entered_champion}** is already in your win-list.", ephemeral=True)
        

class ShowWinsView(View):
    def __init__(self, user_id, ctx):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.ctx = ctx

        # Create the "Show Wins" button and set its callback
        show_wins_button = Button(
            label="Show wins",
            style=discord.ButtonStyle.primary
        )
        show_wins_button.callback = self.show_wins_callback
        self.add_item(show_wins_button)

    async def show_wins_callback(self, interaction: discord.Interaction):
        # Call list_wins with the original context and send the output
        embed, view = await get_wins_embed_and_view(interaction)
        await interaction.response.send_message(embed=embed, view=view)


class ChampionButtonView(View):
    def __init__(self, ctx, champions, reroll_count=0, max_rerolls=2, teammate_name=None):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.champions = champions
        self.reroll_count = reroll_count
        self.max_rerolls = max_rerolls
        self.teammate_name = teammate_name

        # Reroll button
        remaining_rerolls = max_rerolls - reroll_count
        if remaining_rerolls < 0:
            remaining_rerolls = 0
        reroll_button = Button(
            label=f"Reroll ({remaining_rerolls})",
            style=discord.ButtonStyle.primary,
            disabled=reroll_count >= max_rerolls
        )
        reroll_button.callback = self.generate_again
        self.add_item(reroll_button)

        # Next Game button
        next_game_button = Button(
            label="Next Game",
            style=discord.ButtonStyle.success
        )
        next_game_button.callback = self.next_game
        self.add_item(next_game_button)

        # Game Win button
        game_win_button = Button(
            label="Game Win 👑",
            style=discord.ButtonStyle.secondary
        )
        game_win_button.callback = self.game_win
        # self.add_item(game_win_button)

    async def generate_again(self, interaction: discord.Interaction):
        global last_reroll_time
        reroll_timeout = 1 # 2 seconds
        current_time = time.time()

        if current_time - last_reroll_time > reroll_timeout:
            self.reroll_count += 1
            await generate_champions(interaction, self.reroll_count, self.max_rerolls, self.teammate_name)
            last_reroll_time = current_time
        else:
            await interaction.response.defer()
            print("too quick")

        
    async def next_game(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await generate_champions(interaction, 0, 2, self.teammate_name, True)

    async def game_win(self, interaction: discord.Interaction):
        clicked_user = interaction.user
        if clicked_user.name != self.teammate_name:
            winner_champion = self.champions[0]
        else:
            winner_champion = self.champions[1]

        win_timestamp = datetime.now().strftime("%d-%m-%Y %H:%M")
        arena_games = load_arena_games()
        user_key = str(clicked_user.id)
        if user_key not in arena_games:
            arena_games[user_key] = {"name": clicked_user.name, "wins": []}
        elif "wins" not in arena_games[user_key]:
            arena_games[user_key]["wins"] = []

        existing_champions = [win["champion"] for win in arena_games[user_key]["wins"]]
        if winner_champion not in existing_champions:
            arena_games[user_key]["wins"].append({
                "champion": winner_champion,
                "timestamp": win_timestamp
            })
            save_arena_games(arena_games)
            status_message = f"**{winner_champion}** successfully added to your win-list."
        else:
            status_message = f"**{winner_champion}** is already in your win-list."

        embed = discord.Embed(
            title="Champion Win Added",
            description=status_message,
            color=discord.Color.green()
        )

        await interaction.response.send_message(
            embed=embed, view=ShowWinsView(clicked_user.id, self.ctx), ephemeral=True
        )


class RemoveChampionModal(Modal):
    def __init__(self, user_id, ctx):
        super().__init__(title="Remove a Champion from Your Win List")
        self.user_id = user_id
        self.ctx = ctx
        self.champion_input = TextInput(label="Champion Name", placeholder="e.g., Ahri, Zed")
        self.add_item(self.champion_input)


    async def on_submit(self, interaction: discord.Interaction):
        entered_champion = self.champion_input.value.strip()  # Capitalize for consistent formatting
        entered_champion_filtered = next((champion for champion in LOL_CHAMPIONS if champion.lower() == entered_champion.lower()), None)

        # Load existing wins data
        arena_games = load_arena_games()

        # Remove the entered champion from the user's list
        user_key = str(self.user_id)
        if entered_champion_filtered and user_key in arena_games and "wins" in arena_games[user_key]:
            original_count = len(arena_games[user_key]["wins"])
            arena_games[user_key]["wins"] = [
                win for win in arena_games[user_key]["wins"] if win["champion"].lower() != entered_champion_filtered.lower()
            ]
            save_arena_games(arena_games)

            # Check if a champion was actually removed
            if len(arena_games[user_key]["wins"]) < original_count:
                status_message = f"❌**{entered_champion_filtered}** has been removed from your win-list."
            else:
                status_message = f"**{entered_champion_filtered}** is not in your win-list."

            embed, view = await get_wins_embed_and_view(interaction, interaction.user)
            await interaction.response.edit_message(content=status_message, embed=embed, view=view)
        else:
            status_message = f"**{entered_champion}** is not a valid champion."
            await interaction.response.send_message(content=status_message, ephemeral=True)


class AddChampionView(View):
    def __init__(self, user_id, ctx):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.ctx = ctx  # Storing ctx for later use in callbacks
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success)
        self.add_button.callback = self.add_champion_callback
        self.add_item(self.add_button)

    async def add_champion_callback(self, interaction: discord.Interaction):
        # Ensure only the intended user can interact
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("You can only edit your own win list. Use `/wins` to see your own win list.", ephemeral=True)
            return

        # Show the modal to add a champion, passing ctx to the modal
        await interaction.response.send_modal(AddChampionModal(self.user_id, self.ctx))


class RemoveChampionView(View):
    def __init__(self, user_id, ctx):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.ctx = ctx  # Store ctx for later use
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger)
        self.remove_button.callback = self.remove_champion_callback
        self.add_item(self.remove_button)

    async def remove_champion_callback(self, interaction: discord.Interaction):
        # Ensure only the intended user can interact
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("You can only edit your own win list.", ephemeral=True)
            return
        # Pass the stored ctx to RemoveChampionModal
        await interaction.response.send_modal(RemoveChampionModal(self.user_id, self.ctx))
    

class UpdateChampionModal(Modal):
    def __init__(self, user_id, ctx):
        super().__init__(title="Sync wins with Riot")
        self.user_id = user_id
        self.ctx = ctx
        self.summoner_input = TextInput(label="Summoner Name#Tagline", placeholder="e.g., thebausffs#euw")
        self.add_item(self.summoner_input)

    async def on_submit(self, interaction: discord.Interaction):
        input_text = self.summoner_input.value.strip()
        summoner_name, _, tagline = input_text.partition('#')

        if not summoner_name or not tagline:
            await interaction.response.send_message("Please enter a valid format: summoner_name#tagline", ephemeral=True)
            return

        await update_arena_games(interaction, summoner_name, tagline, self.user_id)

class UpdateChampionView(View):
    def __init__(self, user_id, ctx, title):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.ctx = ctx
        self.update_button = Button(label=title, style=discord.ButtonStyle.primary)
        self.update_button.callback = self.update_champion_callback
        self.add_item(self.update_button)

    async def update_champion_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("You can only modify your own win list. Use `/wins` to see your own win list.", ephemeral=True)
            return

        arena_games = load_arena_games()
        user_key = str(self.user_id)
        summoner_name = arena_games.get(user_key, {}).get("summoner_name", None)
        tagline = arena_games.get(user_key, {}).get("summoner_tagline", None)

        if summoner_name and tagline:
            embed, view = await get_wins_embed_and_view(interaction, interaction.user)
            status_message = f"Your wins for **{summoner_name}#{tagline}** are being updated, please wait... ⌛"
            await interaction.response.edit_message(content=status_message, embed=embed, view=view)
            puuid = await riot_api.get_puuid(summoner_name, tagline)
            if puuid:
                latest_update = arena_games.get(user_key, {}).get("latest_update", None)
                user_name = interaction.user.name
                await riot_api.update_arena_games(interaction, user_key, user_name, puuid, LOL_CHAMPIONS, latest_update)
                
                # send new list to user message
                status_message = "Win list updated ✅"
                embed, view = await get_wins_embed_and_view(interaction, interaction.user)
                await interaction.edit_original_response(content=status_message, embed=embed, view=view)
        else:
            await interaction.response.send_modal(UpdateChampionModal(self.user_id, self.ctx))


class SeeAllLeaderboardView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__()
        # Define the 'See All' button
        self.show_more_button = Button(label="See All", style=discord.ButtonStyle.primary)
        self.show_more_button.callback = self.show_more_callback
        self.interaction = interaction  # Store the context to use in callback
        self.add_item(self.show_more_button)

    async def show_more_callback(self, interaction: discord.Interaction):
        # Call list_leaderboard when the button is clicked
        embed, view = await create_leaderboard(interaction)
        await interaction.response.send_message(embed=embed, view=view)
        # You can add an acknowledgment message or update the original message here if needed
        await interaction.response.defer()  # Optionally respond to the interaction without sending a message

class ChangeSummonerNameModal(Modal):
    def __init__(self, user_id, ctx):
        super().__init__(title="Change Your Summoner Name")
        self.user_id = user_id
        self.ctx = ctx
        self.summoner_name_input = TextInput(label="New Summoner Name#Tagline", placeholder="e.g., Thebausffs#euw")
        self.add_item(self.summoner_name_input)


class SearchChampionModal(Modal):
    def __init__(self, user_id, ctx):
        super().__init__(title="Search Champion")
        self.user_id = user_id
        self.ctx = ctx
        self.champion_input = TextInput(label="Enter Champion Name", placeholder="e.g., Ahri, Zed")
        self.add_item(self.champion_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Fetch the entered champion name and search in the champion list
        input_champion = self.champion_input.value.strip()
        await has_won_on_champion(interaction, input_champion)
        return
       
class SearchChampionView(View):
    def __init__(self, user_id, ctx):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.ctx = ctx
        self.search_button = Button(label="Search Champion 🔍", style=discord.ButtonStyle.grey)
        self.search_button.callback = self.search_champion_callback
        self.add_item(self.search_button)

    async def search_champion_callback(self, interaction: discord.Interaction):
        modal = SearchChampionModal(self.user_id, self.ctx)
        await interaction.response.send_modal(modal)

class ChangeSummonerNameButton(Button):
    def __init__(self, user_id, ctx):
        super().__init__(label="Change Summoner Name", style=discord.ButtonStyle.gray)
        self.user_id = user_id
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("You can only edit your own win list. Use `/wins` to see your own win list.", ephemeral=True)
            return
        
        modal = ChangeSummonerNameModal(self.user_id, self.ctx)
        await interaction.response.send_modal(modal)

class ChangeSummonerNameModal(Modal):
    def __init__(self, user_id, ctx):
        super().__init__(title="Change Your Summoner Name")
        self.user_id = user_id
        self.ctx = ctx
        self.summoner_name_input = TextInput(label="New Summoner Name#Tagline", placeholder="e.g., Thebausffs#euw")

        self.add_item(self.summoner_name_input)
    async def on_submit(self, interaction: discord.Interaction):
        input_text = self.summoner_name_input.value.strip()
        summoner_name, _, tagline = input_text.partition('#')
        arena_games = load_arena_games()
        user_key = str(self.user_id)

        if user_key in arena_games:
            await update_arena_games(interaction, summoner_name, tagline, self.user_id)
        else:
            await interaction.response.send_message("No previous summoner data found. Please use the correct method to add a new summoner.", ephemeral=True)


async def update_arena_games(interaction: discord.Interaction, summoner_name: str, tagline: str, user_id: int):
    puuid = await riot_api.get_puuid(summoner_name, tagline)
    if puuid:
        user_key = str(user_id)

        # Notify user that updating might take some time
        await interaction.response.send_message(f"Updating champion wins for **{summoner_name}#{tagline}**. This process may take a few minutes as it's the first time. (approximately 5 minutes ⌛)")
        
        user_name = interaction.user.name
        await riot_api.update_arena_games(interaction, user_key, user_name, puuid, LOL_CHAMPIONS, None, summoner_name, tagline)
        embed, view = await get_wins_embed_and_view(interaction)
        status_message = "Win list synced with Riot Games ✅"
        await interaction.edit_original_response(content=status_message, embed=embed, view=view)
    else:
        await interaction.response.send_message(f"Summoner with name **{summoner_name}** and tagline **{tagline}** doesn't exist", ephemeral=True)
        return
    
# Helper function to save the wins data
def save_arena_games(data):
    with open(GAMES_FILENAME, "w") as file:
        json.dump(data, file, indent=4)

def epoch_to_str(epoch):
    try:
        epoch_time = epoch / 1000  # Convert milliseconds to seconds
        datetime_obj = datetime.fromtimestamp(epoch_time)
        return datetime_obj.strftime('%d/%m/%Y %H:%M')
    except:
        return epoch

def get_wins_as_dict(all_arena_games: dict, user_key):
    arena_games =  all_arena_games.get(user_key, {}).get('arena_games', [])
    if not arena_games:
        return False
    player_games = [values for values in arena_games.values()]
    
    # Ensure player_games is a list and filter entries where 'place' is 1
    first_place_games = [game for game in player_games if game.get('place') == 1]
    # Sort the list of dictionaries based on 'timestamp'
    return sorted(first_place_games, key=lambda x: x['timestamp'])

def get_first_wins_as_dict(wins):
    if not wins:
        return None
    
    champions = set()
    first_wins = []
    for win in wins:
        if win['champion'] not in champions:
            champions.add(win['champion'])
            first_wins.append(win)
    return first_wins

def get_unique_user_wins(arena_games, user_id):
    wins = get_wins_as_dict(arena_games, user_id)
    return list({win['champion'] for win in wins}) if wins else []


async def get_wins_embed_and_view(interaction, target_user=None):
    # Determine which user's data to display
    user_key = str(target_user.id) if target_user else str(interaction.user.id)
    user_name = target_user.name if target_user else interaction.user.name

    # Load the arena games from storage
    arena_games = load_arena_games()
    user_data = arena_games.get(user_key, {})

    # Extract relevant user data
    summoner_name = user_data.get("summoner_name", user_name)
    summoner_tagline = user_data.get("summoner_tagline", "")
    latest_update = user_data.get("latest_update", None)

    # Get the wins from the arena games
    wins = get_wins_as_dict(arena_games, user_key)
    first_wins = get_first_wins_as_dict(wins)
    
    last_updated = epoch_to_str(latest_update) if latest_update else "Not updated"
    extra_notice = ""
    if summoner_name and summoner_tagline:
        extra_notice = f"\n\n_The bot has likely been updated. Please click below to retrieve your wins again. \nAfter updating, remember to use the new /stats function. 😀_"

    # Generate a description of the first wins
    game_details_description = "\n".join([
        f"• **{game['champion']}** - First win with {game['teammate_name']} as {game['teammate_champion']} on {epoch_to_str(game['timestamp'])}"
        for game in first_wins
    ]) if first_wins else "No recorded wins." + extra_notice

    # Create a summary of total wins and the last update
    if wins:
        total_unique_wins = len(first_wins)
        final_description = f"{game_details_description}\n\n **Total unique wins: {total_unique_wins}/60** \n_(Last Updated: {last_updated}_)"
    else:
        final_description = game_details_description
    # Generate the title of the embed using summoner information
    title_username = f"{summoner_name}#{summoner_tagline}" if summoner_name and summoner_tagline else user_name
    embed = discord.Embed(title=f"{title_username}'s Win List 👑", description=final_description, color=discord.Color.green())

    # Create a view and add appropriate buttons
    view = View()
    if summoner_name and summoner_tagline:
        view.add_item(UpdateChampionView(user_key, interaction, "Update 🔁").children[0])
        if wins and len(wins) > 0:
            view.add_item(SearchChampionView(user_key, interaction).children[0])
        view.add_item(ChangeSummonerNameButton(user_key, interaction))
    else:
        view.add_item(UpdateChampionView(user_key, interaction, "Sync with Riot 🔁").children[0])

    return embed, view


@tree.command(
    name="wins",
    description="Shows your wins",
)
@app_commands.describe(member="Show wins of specific user")
async def list_wins(interaction: discord.Interaction, member: discord.Member = None):
    embed, view = await get_wins_embed_and_view(interaction, member)
    await interaction.response.send_message(embed=embed, view=view)


def split_leaderboard(leaderboard, length=3):
    limited_items = {}
    for key, value in leaderboard.items():
        limited_items[key] = value
        if len(limited_items) == length:
            break
    return limited_items

@tree.command(
    name="leaderboard_image",
    description="Shows leaderboard image (WORK IN PROGRESS)",
)
async def send_leaderboard_image(interaction: discord.Interaction):
    # Acknowledge the interaction and inform the user that the image is being generated.
    await interaction.response.defer()  # Use ephemeral if you want it to be visible only to the user
    await interaction.followup.send("Generating the leaderboard image, please wait...")

    # Generate the leaderboard image
    wins_data = load_arena_games()
    leaderboard = {id: len(info['wins']) for id, info in wins_data.items() if discord.utils.get(interaction.guild.members, name=info['name'])}

    # Sort and split the leaderboard
    leaderboard = dict(sorted(leaderboard.items(), key=lambda item: item[1], reverse=True))
    avatar_info = [fetch_discord_avatar_and_username(user_id, BOT_TOKEN) for user_id in leaderboard.keys()]
    file_path = await generate_leaderboard_with_avatars(leaderboard, avatar_info)

    # Replace the loading message with the actual image
    file = discord.File(file_path, filename="leaderboard.png")
    view = SeeAllLeaderboardView(interaction=interaction)  # Initialize the view with the current context
    await interaction.edit_original_response(content="", attachments=[file], view=view)


async def create_leaderboard(interaction: discord.Interaction): 
    all_arena_games = load_arena_games()
    leaderboard = {}

    for user_id, info in all_arena_games.items():
        user = discord.utils.get(interaction.guild.members, name=info['name'])
        if user:
            wins = get_unique_user_wins(all_arena_games, user_id)
            leaderboard[info['name']] = len(wins)

    leaderboard_sorted = dict(sorted(leaderboard.items(), key=lambda item: item[1], reverse=True))
    description = "\n".join([f"#{i+1} **{name}**:{total} win{'s' if total != 1 else ''}" \
                             for i, (name, total) in enumerate(leaderboard_sorted.items())])
    embed = discord.Embed(
        title="Leaderboard 🏆",
        description=description,
        color=discord.Color.orange()
    ) 

    view = View()
    return embed, view

@tree.command(
    name="leaderboard",
    description="Show leaderboard of server",
)
async def list_leaderboard(interaction: discord.Interaction):
    embed, view = await create_leaderboard(interaction)
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(
    name="help",
    description="Show available commands",
)
async def list_commands(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Arena Commands",
        description="Here are the available commands",
        color=discord.Color.blue()
    )

    commands = [
        "`/teams [members]` \nGenerate random teams based on players in the current voice channel, or specified members.",
        "`/champions [member]` \nGenerate random champions for yourself or with specified teammate.",
        "`/wins [username]` \nShow the win list of the command issuer or a specified user.",
        "`/leaderboard` \nShow leaderboard of current server."
    ]

    for command in commands:
        embed.add_field(
            name="",
            value=command,
            inline=False
        )

    # Create a View with buttons and attach it to the embed
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(
    name="champions",
    description="Generate 2 random champions",
)
@app_commands.describe(teammate="Type the name of your teammate to generate a team of 2 champions")
async def champions(interaction: discord.Interaction, teammate: discord.Member = None):
    if teammate:
        await generate_champions(interaction, 0, 2, teammate.name)
    else:
        await generate_champions(interaction)


@tree.command(
    name="teams",
    description="Generate teams from selected server members or voice channel",
)
@app_commands.describe(select_members="Set to yes to select members manually.")
@app_commands.choices(select_members=[
    app_commands.Choice(name="yes", value="yes"),
    app_commands.Choice(name="no", value="no")
])
async def generate_teams(interaction: discord.Interaction, select_members: str = "no"):
    if select_members == "yes":
        voice_state = interaction.user.voice
        if voice_state and voice_state.channel:
            members = [member for member in voice_state.channel.members if not member.bot]
            if len(members) >= 2:
                if members:
                    view = TeamMemberSelectionView(members)
                    await interaction.response.send_message("Select members that play game:", view=view)
                else:
                    await interaction.response.send_message("No members available for selection.", ephemeral=True)
            else:
                await interaction.response.send_message("You must be with at least 2 players in the voice channel", ephemeral=True)
        else:
            await interaction.response.send_message("You need to be in a voice channel to use this command!", ephemeral=True)
    else:
        # Generate teams from voice channel members
        voice_state = interaction.user.voice
        if voice_state and voice_state.channel:
            members = [member for member in voice_state.channel.members if not member.bot]
            if len(members) >= 2:
                random.shuffle(members)
                teams = [members[i:i + 2] for i in range(0, len(members), 2)]
                solo_player_display = None
                if len(members) % 2 == 1:
                    solo_player = teams[-1].pop()
                    teams[-1].append(solo_player)  # Keep as member
                    solo_player_display = solo_player.name

                description_lines = []
                for i, team in enumerate(teams):
                    if solo_player_display and i == len(teams) - 1:  # Check if this is the last team with a solo player
                        description_lines.append(f"Team {i+1}: {', '.join(member.name for member in team[:-1])}, {solo_player_display}")
                    else:
                        description_lines.append(f"Team {i+1}: {', '.join(member.name for member in team)}")
                
                description = "\n".join(description_lines)
                embed = discord.Embed(
                    title="Teams for Arena",
                    description=description,
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("Not enough members in the voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("You need to be in a voice channel to use this command!", ephemeral=True)

async def get_user_arena_stats(user_id: str):
    """Retrieve a list of arena win statistics for a given user."""

    # Load all arena game wins from storage
    arena_games = load_arena_games()

    # Check if the user has any recorded wins
    if user_id not in arena_games:
        return []

    # Extract the list of win statistics for the specified user
    user_wins = arena_games[user_id]['arena_games']
    if not user_wins:
        return []
    stats = [user_wins[game_id] for game_id in user_wins]

    return stats

async def arena_stats_to_description(user_id):
    stats = await get_user_arena_stats(user_id)
    if not stats:
        return None
    
    def get_most_played_champions():
        # Accumulate the count of each champion played
        champion_count = {}
        for game in stats:
            champion = game['champion']
            if champion in champion_count:
                champion_count[champion] += 1
            else:
                champion_count[champion] = 1

        # Sort the champions based on the count, highest first
        champion_count_sorted = sorted(champion_count.items(), key=lambda item: item[1], reverse=True)
        
        # Get the first five most played champions
        first_five_dict = dict(champion_count_sorted[:5])
        
        # Return as a formatted string
        return '\n'.join(f"• **{champ}**: {count} times" for champ, count in first_five_dict.items())

    def get_average_place():
        if not stats:
            return 0  # Avoid division by zero
        return sum(game['place'] for game in stats) / len(stats)

    def get_total_kda():
        kills, deaths, assists = 0, 0, 0
        for game in stats:
            kills += game['stats'].get('total_kills', 0)
            deaths += game['stats'].get('total_deaths', 0)
            assists += game['stats'].get('total_assists', 0)
        return f"{kills}/{deaths}/{assists}"

    def get_total_healing():
        return sum(game['stats'].get('total_heal', 0) for game in stats)

    def get_total_shielding():
        return sum(game['stats'].get('total_shielding_on_teammate', 0) for game in stats)

    def get_placement_stats():
        if not stats:
            return {"top_1_percent": 0, "top_4_percent": 0, "last_place_percent": 0}
        placements = [game['place'] for game in stats]
        total_games = len(placements)
        top_1 = sum(1 for p in placements if p == 1)
        top_4 = sum(1 for p in placements if p <= 4)
        last_place = sum(1 for p in placements if p == 8)
        return {
            "top_1": top_1,
            "top_4": top_4,
            "last_place": last_place
        }

    def get_most_stat(stat_key):
        max_value = 0
        max_champion = ""
        for game in stats:
            if 'stats' in game:
                stat_value = game['stats'].get(stat_key, 0)
                if stat_value > max_value:
                    max_value = stat_value
                    max_champion = game['champion']
        if max_champion:  # Ensures that we found at least one valid game
            return (max_value, max_champion)
        else:
            return (0, "No data")  # or any other default you'd prefer
        
    def get_most_ability_usage():
        return max(
            (sum(game['stats'].get(stat, 0) for stat in ['ability_1_used', 'ability_2_used', 'ability_3_used', 'ability_4_used']),
            game['champion'],
            max(('Q', game['stats'].get('ability_1_used', 0)),
                ('W', game['stats'].get('ability_2_used', 0)),
                ('E', game['stats'].get('ability_3_used', 0)),
                ('R', game['stats'].get('ability_4_used', 0)), key=lambda x: x[1]))
            for game in stats
        )
    
    # Building the description
    placement_stats = get_placement_stats()
    most_damage = get_most_stat('total_damage')
    total_usage, champion, (most_used_ability, count) = get_most_ability_usage()
    most_cc_duration = get_most_stat('cc_duration')
    most_gold = get_most_stat('gold_earned')
    highest_crit = get_most_stat('highest_crit')
    largest_killing_spree = get_most_stat('largestKillingSpree')
    total_heal = get_total_healing()
    total_shield = get_total_shielding()
    most_heal = get_most_stat('total_heal') 

    description_items = [
        f"**Total games played**: {len(stats)} \n {get_most_played_champions()}",
        "",
        f"**Total #1**: {placement_stats['top_1']} ({(100 * placement_stats['top_1'] / len(stats)):.1f}%)",
        f"**Total top 4**: {placement_stats['top_4']} ({(100 * placement_stats['top_4'] / len(stats)):.1f}%)",
        f"**Total last place**: {placement_stats['last_place']} ({(100 * placement_stats['last_place'] / len(stats)):.1f}%)",
        f"**Average placement**: {get_average_place():.1f}",
        "",
        f"**Total K/D/A**: {get_total_kda()}",
        f"**Total healing**: {total_heal} ({total_heal / len(stats):.1f} avg)",
        f"**Total shielding**: {total_shield} ({total_shield / len(stats):.1f} avg)",
        "",
        f"**Largest killing spree**: {largest_killing_spree[1]} ({largest_killing_spree[0]} kills)",
        f"**Most damage in one game**: {most_damage[1]} ({most_damage[0]} damage)",
        f"**Most healing in one game**: {most_heal[1]} ({most_heal[0]} healing)",
        f"**Most ability used in one game**: {champion} {most_used_ability} ({count} times)",
        f"**Most cc duration in one game**: {most_cc_duration[1]} ({most_cc_duration[0]} seconds)",
        f"**Most gold earned in one game**: {most_gold[1]} ({most_gold[0]} gold)",
        f"**Highest crit**: {highest_crit[1]} ({highest_crit[0]} damage)"
    ]
    return "\n".join(description_items)

async def get_stats_embed(user_id: str):
    arena_games = load_arena_games()
    summoner_name = arena_games.get(user_id, {}).get("summoner_name", None)
    description = await arena_stats_to_description(user_id)
    if not description:
        return None
    
    embed = discord.Embed(
            title=f"Stats for {summoner_name}",
            description=description,
            color=discord.Color.green()
        )
    return embed

@tree.command(
    name="stats",
    description="Show intersting stats!",
)
@app_commands.describe(summoner_name="Name of the summoner")
async def haswon(interaction: discord.Interaction, summoner_name: discord.Member = None):
    user_id = str(interaction.user.id)
    if summoner_name:
        target_user = discord.utils.get(interaction.guild.members, name=summoner_name.name)
        if not target_user:
            await interaction.response.send_message(f"User not found. Please try again.", ephemeral=True)
            return
        user_id = str(target_user.id)

    embed = await get_stats_embed(user_id)
    if not embed:
        await interaction.response.send_message(f"No games found for this user. Use `/wins` to update your wins.", ephemeral=True)
        return
    await interaction.response.send_message(embed=embed)

async def hasWon(interaction: discord.Interaction, entered_champion: str):
    def normalize_name(name):
        return name.lower().replace("'", "").replace(" ", "").replace(".", "")

    all_arena_games = load_arena_games()
    user_id = str(interaction.user.id)
    unique_user_wins = get_unique_user_wins(all_arena_games, user_id)
    champion_name = next((champion for champion in LOL_CHAMPIONS if normalize_name(champion) == normalize_name(entered_champion)),None)

    if not champion_name:
        return None, None
    return champion_name in unique_user_wins, champion_name

async def has_won_on_champion(interaction: discord.Interaction, champion: str = None):
    if champion:
        haswon, champ_name_normalized = await hasWon(interaction, champion)
        if haswon == None:
            await interaction.response.send_message(f"❓Champion **{champion}** does not exist.", ephemeral=True)
        elif haswon == True:
            await interaction.response.send_message(f"🥇 You have won on **{champ_name_normalized}**.", ephemeral=True)
        elif haswon == False:
            await interaction.response.send_message(f"😢 You have not won on **{champ_name_normalized}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Please provide a champion name.", ephemeral=True)

@tree.command(
    name="haswon",
    description="See if you have already won on a champion",
)
@app_commands.describe(champion="Name of the champion")
async def haswon(interaction: discord.Interaction, champion: str = None):
    await has_won_on_champion(interaction, champion)
    return
    
async def generate_champions(interaction: discord.Interaction, reroll_count=0, max_rerolls=2, teammate_name=None, is_next_game=False):
    author = interaction.user.name 
    user_id = str(interaction.user.id)  
    teammate_name = None if teammate_name == "Teammate" else teammate_name

    if teammate_name == author:
        await interaction.response.send_message("You can not team up with yourself.", ephemeral=True)
        return

    arena_games = load_arena_games()
    user_wins = get_unique_user_wins(arena_games, user_id)
    available_for_user = [champion for champion in LOL_CHAMPIONS if champion not in user_wins]
    if not available_for_user:
        await interaction.response.send_message(f"{author}, you have won with all available champions.")
        return
    
    user_champion = random.choice(available_for_user)

    if teammate_name:
        target_user = discord.utils.get(interaction.guild.members, name=teammate_name)
        if not target_user:
            await interaction.response.send_message(f"User **{teammate_name}** not found.")
            return
        teammate_name_actual = teammate_name
        teammate_wins = get_unique_user_wins(arena_games, str(target_user.id))
        available_for_teammate = [champion for champion in LOL_CHAMPIONS if champion not in teammate_wins and champion != user_champion]
        if not available_for_teammate:
            await interaction.response.send_message(f"{teammate_name_actual}, you have won with all available champions.")
            return
        teammate_champion = random.choice(available_for_teammate)
    else:
        teammate_name_actual = "Teammate"
        available_for_teammate = [champion for champion in LOL_CHAMPIONS if champion != user_champion]
        teammate_champion = random.choice(available_for_teammate)

    def clean_name(name):
        return name.lower().replace("'", "").replace(" ", "").replace(".", "")

    user_champion_url = f"https://blitz.gg/lol/champions/{clean_name(user_champion)}/arena"
    user_hyperlink = f"[{user_champion}]({user_champion_url})"
    teammate_champion_url = f"https://blitz.gg/lol/champions/{clean_name(teammate_champion)}/arena"
    teammate_hyperlink = f"[{teammate_champion}]({teammate_champion_url})"

    description = f"{author}: {user_hyperlink}\n{teammate_name_actual}: {teammate_hyperlink} \
                        \n\n _This excludes the champions you've won with._"
    
    embed = discord.Embed(
        title="Random Champions",
        description=description,
        color=discord.Color.orange()
    )

    view = ChampionButtonView(interaction, [user_champion, teammate_champion], reroll_count, max_rerolls, teammate_name_actual)

    if is_next_game:
        await interaction.followup.send(embed=embed, view=view) 
    elif reroll_count == 0:
        await interaction.response.send_message(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)

def github_status():
    try:
        # Fetch the latest changes from the remote
        subprocess.run(["git", "fetch"], check=True)

        # Check the difference between the local branch and the remote branch
        local_branch = subprocess.run(
            ["git", "rev-parse", "@"],
            check=True,
            stdout=subprocess.PIPE,
            text=True
        ).stdout.strip()
        
        remote_branch = subprocess.run(
            ["git", "rev-parse", "@{u}"],
            check=True,
            stdout=subprocess.PIPE,
            text=True
        ).stdout.strip()
        
        # Check for differences between local and remote branches
        if local_branch == remote_branch:
            print("Your local branch is up to date.")
        else:
            print("Your local branch is not up to date with the remote branch.")
            # Optionally, provide instructions for updating
            print("Consider pulling the latest changes with 'git pull'.")
    except subprocess.CalledProcessError as e:
        print("Verifying Git Status: Error while checking repository status:", e)
    except Exception as e:
        print("Verifying Git Status: An unexpected error occurred, probably because git is not installed.", e)

def fetch_discord_avatar_and_username(user_id, BOT_TOKEN):
    """Fetches the Discord avatar and username for a given user ID using the specified bot token."""
    url = f"https://discord.com/api/v9/users/{user_id}"
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        avatar_hash = data.get('avatar')
        username = data.get('username', 'Unknown User')
        if avatar_hash:
            avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=1024"
            return avatar_url, username
        return "path_to_default_avatar.png", username
    else:
        print(f"Failed to fetch data for user {user_id}: {response.status_code} - {response.text}")
        return "path_to_default_avatar.png", 'Unknown User'


async def generate_leaderboard_with_avatars(leaderboard_data, avatar_info):
    """Generates and saves a leaderboard image with avatars, usernames, and scores."""
    if not os.path.exists('leaderboards'):
        os.makedirs('leaderboards')

    background = Image.open('assets/leaderboard_bg1.png').convert('RGBA')
    fonts = {
        0: ImageFont.truetype("assets/Heavitas.ttf", 28),  # Larger font for 1st place
        1: ImageFont.truetype("assets/Heavitas.ttf", 20),  # Standard font for others
        2: ImageFont.truetype("assets/Heavitas.ttf", 20)
    }

    # Configuration for avatar and text placement
    config = [
        {"coords": (414, 250, 152, 152), "text_offset": (420, 420)},  # First place
        {"coords": (245, 250, 105, 105), "text_offset": (255, 365)},  # Second place
        {"coords": (630, 250, 105, 105), "text_offset": (640, 365)}   # Third place
    ]

    draw = ImageDraw.Draw(background)
    sorted_leaderboard = sorted(leaderboard_data.items(), key=lambda item: item[1], reverse=True)[:3]
    
    for index, ((user_id, score), (avatar_url, username)) in enumerate(zip(sorted_leaderboard, avatar_info)):
        avatar_image = Image.open(BytesIO(requests.get(avatar_url).content) if avatar_url.startswith('http') else avatar_url)
        avatar_image = avatar_image.convert('RGBA').resize((config[index]["coords"][2], config[index]["coords"][3]))
        mask = avatar_image.split()[3] if 'A' in avatar_image.getbands() else None
        background.paste(avatar_image, config[index]["coords"][:2], mask)
        draw.text(config[index]["text_offset"], f"{score} Wins", font=fonts[index], fill='#553EF9')

    file_path = 'leaderboards/leaderboard_with_avatars.png'
    background.save(file_path)
    return file_path


@tree.command(
    name="sync",
    description="Owner only",
)
async def sync(interaction: discord.Interaction):
    if str(interaction.user.id) == env.get("OWNER_ID"):
        if GUILD_ID:
            # Register commands to a specific guild for debugging
            guild = discord.Object(id=int(GUILD_ID))
            tree.copy_global_to(guild=guild)
            synced = await tree.sync(guild=guild)
        else:
            # Register commands globally for production
            synced = await tree.sync()
        await interaction.response.send_message(f'✅ {len(synced)} commands synced', ephemeral=True)
    else:
        await interaction.response.send_message('You must be the owner to use this command!', ephemeral=True)

    
@client.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("I don't have permission to do that. Please check my role permissions.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CommandInvokeError):
        print(error)
        await ctx.send("An error occurred while executing the command. Make sure I have the necessary permissions.")
    else:
        await ctx.send(f"An unexpected error occurred: {error}")

def clear_wins():
    arena_games = load_arena_games()
    for user_id in arena_games:
        arena_games[user_id]['arena_games'] = {}
        arena_games[user_id]['latest_update'] = None
    save_arena_games(arena_games)

# Check github status
github_status()

# Clear wins every time program gets updated to match with the latest version, except for development
if not env.get('BOT_TOKEN_DEV'):
    clear_wins()

# Start the program
client.run(BOT_TOKEN)

