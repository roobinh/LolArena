import os, json, random, discord, subprocess, requests
from dotenv import dotenv_values
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

def load_champion_list(file_path="LOL_CHAMPIONS.json"):
    with open(file_path, "r") as file:
        data = json.load(file)
    return data["champions"]

# Helper function to load or initialize the wins data
def load_champion_wins():
    if os.path.exists(WINS_FILE):
        try:
            with open(WINS_FILE, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return {}
    return {}

# List of League of Legends champions
LOL_CHAMPIONS = load_champion_list()
WINS_FILE = "champion_wins.json"

# Dictionary to store assigned numbers to players
player_numbers = {}

# Get tokens
env = dotenv_values('.env')
BOT_TOKEN = env.get('BOT_TOKEN_DEV') or env.get('BOT_TOKEN')
GUILD_ID = env.get("GUILD_ID", None)
print(f"GUILD_ID = {GUILD_ID}")

# Bot Variables
intents = discord.Intents.all()
intents.voice_states = True
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

        
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

        champion_wins = load_champion_wins()
        user_key = str(self.user_id)
        
        champion_wins = load_champion_wins()
        user_key = str(self.user_id)
        if user_key not in champion_wins:
            champion_wins[user_key] = {"name": interaction.user.name, "wins": []}
        elif "wins" not in champion_wins[user_key]:
            champion_wins[user_key]["wins"] = []

        existing_champions = [win["champion"] for win in champion_wins[user_key]["wins"]]
        if entered_champion not in existing_champions:
            champion_wins[user_key]["wins"].append({
                "champion": entered_champion,
                "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M")
            })
            save_champion_wins(champion_wins)
            
            # Fetch the new embed and view with the updated win list
            embed, view = await get_wins_embed_and_view(interaction, interaction.user)
            status_message = f"**{entered_champion}** has been successfully added to your win list."
            await interaction.response.edit_message(content=status_message, embed=embed, view=view)
        else:
            await interaction.response.send_message(content=f"**{entered_champion}** is already in your win-list.", ephemeral=True)
        
        
class ArenaHelpView(View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

        # Create buttons for different commands
        teams_button = Button(
            label="Generate Teams",
            style=discord.ButtonStyle.success  # Green
        )
        teams_button.callback = self.generate_teams
        self.add_item(teams_button)

        champions_button = Button(
            label="Generate Champions",
            style=discord.ButtonStyle.primary  # Yellow not available, so using primary (blue)
        )
        champions_button.callback = self.generate_champions
        self.add_item(champions_button)

        list_button = Button(
            label="List All Players",
            style=discord.ButtonStyle.secondary  # Blue
        )
        list_button.callback = self.list_players
        self.add_item(list_button)

    async def generate_teams(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Acknowledge the interaction
        await generate_teams(self.ctx)

    async def generate_champions(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Acknowledge the interaction
        await generate_champions(self.ctx)

    async def list_players(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Acknowledge the interaction
        await list_players(self.ctx)


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
        await list_wins(self.ctx)
        # Acknowledge the interaction to confirm that the button click was processed
        await interaction.response.defer()


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
        self.add_item(game_win_button)

    async def generate_again(self, interaction: discord.Interaction):
        self.reroll_count += 1
        await generate_champions(interaction, self.reroll_count, self.max_rerolls, self.teammate_name)

    async def next_game(self, interaction: discord.Interaction):
        clicked_user = interaction.user.name
        await interaction.response.defer()
        await generate_champions(None, 0, 2, clicked_user)

    async def game_win(self, interaction: discord.Interaction):
        clicked_user = interaction.user
        author = self.ctx.author

        if clicked_user == author:
            winner_champion = self.champions[0]
        else:
            winner_champion = self.champions[1]

        win_timestamp = datetime.now().strftime("%d-%m-%Y %H:%M")
        champion_wins = load_champion_wins()
        user_key = str(clicked_user.id)
        if user_key not in champion_wins:
            champion_wins[user_key] = {"name": clicked_user.name, "wins": []}
        elif "wins" not in champion_wins[user_key]:
            champion_wins[user_key]["wins"] = []

        existing_champions = [win["champion"] for win in champion_wins[user_key]["wins"]]
        if winner_champion not in existing_champions:
            champion_wins[user_key]["wins"].append({
                "champion": winner_champion,
                "timestamp": win_timestamp
            })
            save_champion_wins(champion_wins)
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
        champion_wins = load_champion_wins()

        # Remove the entered champion from the user's list
        user_key = str(self.user_id)
        if entered_champion_filtered and user_key in champion_wins and "wins" in champion_wins[user_key]:
            original_count = len(champion_wins[user_key]["wins"])
            champion_wins[user_key]["wins"] = [
                win for win in champion_wins[user_key]["wins"] if win["champion"].lower() != entered_champion_filtered.lower()
            ]
            save_champion_wins(champion_wins)

            # Check if a champion was actually removed
            if len(champion_wins[user_key]["wins"]) < original_count:
                status_message = f"**{entered_champion_filtered}** has been removed from your win-list."
            else:
                status_message = f"**{entered_champion_filtered}** is not in your win-list."

            embed, view = await list_wins(self.ctx, interaction.user, as_embed=True)
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
            await interaction.response.send_message("You can only edit your own win list. Use `/arena wins` to see your own win list.", ephemeral=True)
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


class SeeAllLeaderboardView(View):
    def __init__(self, ctx):
        super().__init__()
        # Define the 'See All' button
        self.show_more_button = Button(label="See All", style=discord.ButtonStyle.primary)
        self.show_more_button.callback = self.show_more_callback
        self.ctx = ctx  # Store the context to use in callback
        self.add_item(self.show_more_button)

    async def show_more_callback(self, interaction: discord.Interaction):
        # Call list_leaderboard when the button is clicked
        await list_leaderboard(self.ctx)
        # You can add an acknowledgment message or update the original message here if needed
        await interaction.response.defer()  # Optionally respond to the interaction without sending a message


@client.event
async def on_ready():
    try:
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    

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


# Helper function to save the wins data
def save_champion_wins(data):
    with open(WINS_FILE, "w") as file:
        json.dump(data, file, indent=4)

async def get_wins_embed_and_view(interaction, target_user=None):
    # If no target user is specified, use the user who initiated the interaction
    user_key = str(target_user.id) if target_user else str(interaction.user.id)
    user_name = target_user.display_name if target_user else interaction.user.display_name

    champion_wins = load_champion_wins()
    wins = champion_wins.get(user_key, {}).get("wins", [])
    description = "\n".join([f"• **{win['champion']}** (_{win['timestamp']}_)" for win in wins]) + f"\n\n_{len(wins)} out of {len(LOL_CHAMPIONS)} champions_" if wins else "No wins recorded."
    embed = discord.Embed(title=f"{user_name}'s Win List 👑", description=description, color=discord.Color.green())

    view = View()
    view.add_item(RemoveChampionView(user_key, interaction).children[0])
    view.add_item(AddChampionView(user_key, interaction).children[0])

    return embed, view

@tree.command(
    name="wins",
    description="Shows your wins",
    guild=discord.Object(id=GUILD_ID)
)
async def list_wins(interaction: discord.Interaction, target_user: discord.Member = None):
    embed, view = await get_wins_embed_and_view(interaction, target_user)
    await interaction.response.send_message(embed=embed, view=view)



def split_leaderboard(leaderboard, length=3):
    limited_items = {}
    for key, value in leaderboard.items():
        limited_items[key] = value
        if len(limited_items) == length:
            break
    return limited_items

async def send_leaderboard_image(ctx):
    wins_data = load_champion_wins()
    leaderboard = {}

    for id, info in wins_data.items():
        user = discord.utils.get(ctx.guild.members, name=info['name'])
        if user:
            leaderboard[id] = len(info['wins'])

    leaderboard = dict(sorted(leaderboard.items(), key=lambda item: item[1], reverse=True))
    leaderboard = split_leaderboard(leaderboard)
    
    # Fetch avatars and usernames
    avatar_info = [fetch_discord_avatar_and_username(user_id, BOT_TOKEN) for user_id in leaderboard.keys()]

    # Generate the leaderboard image
    file_path = generate_leaderboard_with_avatars(leaderboard, avatar_info)

    # Send the image to the Discord channel
    file = discord.File(file_path, filename="leaderboard.png")
    view = SeeAllLeaderboardView(ctx)  # Initialize the view with the current context
    await ctx.send(file=file, view=view)


async def list_leaderboard(ctx):
    WINS_FILE = load_champion_wins()
    leaderboard = {}

    for info in WINS_FILE.values():
        user = discord.utils.get(ctx.guild.members, name=info['name'])
        if user:
            leaderboard[info['name']] = len(info['wins'])

    leaderboard_sorted = dict(sorted(leaderboard.items(), key=lambda item: item[1], reverse=True))
    description = "\n".join([f"#{i+1} **{name}**:{total} win{'s' if total != 1 else ''}" \
                             for i, (name, total) in enumerate(leaderboard_sorted.items())])
    embed = discord.Embed(
        title="Leaderboard 🏆",
        description=description,
        color=discord.Color.orange()
    ) 

    view = View()
    await ctx.send(embed=embed, view=view)

@tree.command(
    name="help",
    description="Show available commands",
    guild=discord.Object(id=GUILD_ID)
)
async def list_commands(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Arena Commands",
        description="Here are the available commands for the arena:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="/arena [user numbers]",
        value="Generate random teams based on players in the current voice channel, or specified numbers (see /arena players).",
        inline=False
    )
    embed.add_field(
        name="/arena champions [username]",
        value="Generate random champions for yourself or with specified teammate.",
        inline=False
    )
    embed.add_field(
        name="/arena wins [username]",
        value="Show the win list of the command issuer or a specified user.",
        inline=False
    )
    embed.add_field(
        name="/arena players",
        value="List all players in the current voice channel.",
        inline=False
    )
    embed.add_field(
        name="/arena help",
        value="Show this help message with detailed information about all commands.",
        inline=False
    )

    # Create a View with buttons and attach it to the embed
    await interaction.response.send_message(embed=embed, view=ArenaHelpView(interaction))


async def list_players(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        voice_channel = ctx.author.voice.channel
        members = voice_channel.members

        embed = discord.Embed(
            title=f"List of players in {voice_channel.name}",
            color=discord.Color.blue()
        )
        for member in members:
            if member.id not in player_numbers:
                player_numbers[member.id] = len(player_numbers) + 1
            embed.add_field(name=f"{player_numbers[member.id]}", value=member.name, inline=False)
        await ctx.send(embed=embed)
    else:
        print("hallo")
        await ctx.send("You need to be in a voice channel to use this command!")


@tree.command(
    name="champions",
    description="Generate 2 random champions NEW",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.describe(teammate="Type the name of your teammate to generate a team of 3 champions")
async def champions(ctx: commands.Context, teammate: str = None):
    print("command_champions")
    if teammate:
        member = discord.utils.get(ctx.guild.members, display_name=teammate)
        if member:
            await generate_champions(ctx, 0, 2, member.display_name)
        else:
            await ctx.send("Member not found.")
    else:
        await generate_champions(ctx)

@tree.command(
    name="teams",
    description="Generate teams of members in voice channel",
    guild=discord.Object(id=GUILD_ID)
)
async def generate_teams(interaction: discord.Interaction):
    voice_state = interaction.user.voice  # Get the voice state of the user who triggered the interaction
    if voice_state and voice_state.channel:
        voice_channel = voice_state.channel
        members = [member for member in voice_channel.members if not member.bot]

        if len(members) == 0:
            await interaction.response.send_message("No players match these numbers. Check `/arena list` for more information.")
        else:
            random.shuffle(members)
            teams = []
            while len(members) > 1:
                team = [members.pop().display_name, members.pop().display_name]
                teams.append(team)
            if members:
                solo = members.pop().display_name
                teams.append([solo])

            embed = discord.Embed(
                title="Teams for Arena",
                description="\n".join([f"Team {i+1}: {', '.join(team)}" for i, team in enumerate(teams)]),
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("You need to be in a voice channel to use this command!")



async def generate_champions(interaction, reroll_count=0, max_rerolls=2, teammate_name=None):
    author = interaction.user.name 
    user_id = interaction.user.id  
    teammate_name = None if teammate_name == "Teammate" else teammate_name
    champion_wins = load_champion_wins()
    user_wins = [win["champion"] for win in champion_wins.get(str(user_id), {}).get("wins", [])]
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
        teammate_id = target_user.id
        teammate_name_actual = teammate_name
        teammate_wins = [win["champion"] for win in champion_wins.get(str(teammate_id), {}).get("wins", [])]
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
        return name.lower().replace("'", "").replace(" ", "")

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
    if reroll_count == 0:
        await interaction.response.send_message(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)

# Note: You also need to adjust how you call generate_champions in command_champions


def is_git_repo_up_to_date():
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

def generate_leaderboard_with_avatars(leaderboard_data, avatar_info):
    """Generates and saves a leaderboard image with avatars, usernames, and scores."""
    if not os.path.exists('leaderboards'):
        os.makedirs('leaderboards')

    background = Image.open('assets/leaderboard_bg1.png').convert('RGBA')
    fonts = {
        0: ImageFont.truetype("assets/Heavitas.ttf", 28),  # Larger font for 1st place
        1: ImageFont.truetype("assets/Heavitas.ttf", 18),  # Smaller font for 2nd place
        2: ImageFont.truetype("assets/Heavitas.ttf", 18)   # Smaller font for 3rd place
    }

    # Define placement coordinates and sizes for each position based on the number of entries
    num_entries = len(leaderboard_data)
    if num_entries == 1:
        placements = {0: (371, 238, 119, 119)}  # Only first place
        text_offsets = {0: (371, 370)}
    elif num_entries == 2:
        placements = {0: (239, 238, 119, 119), 1: (547, 238, 119, 119)}  # First and second places swapped
        text_offsets = {0: (239, 370), 1: (547, 370)}
    else:
        placements = {0: (547, 238, 77, 77), 1: (371, 238, 119, 119), 2: (239, 238, 77, 77)}
        text_offsets = {0: (547, 325), 1: (371, 370), 2: (239, 325)}

    draw = ImageDraw.Draw(background)
    for index, ((user_id, score), (avatar_url, username)) in enumerate(zip(sorted(leaderboard_data.items(), key=lambda item: item[1], reverse=True)[:3], avatar_info)):
        if avatar_url.startswith('http'):
            response = requests.get(avatar_url)
            avatar_image = Image.open(BytesIO(response.content))
        else:
            avatar_image = Image.open(avatar_url)  # Open from local path if URL is not valid

        avatar_image = avatar_image.convert('RGBA')
        x, y, width, height = placements[index]
        avatar_image = avatar_image.resize((width, height))
        mask = avatar_image.split()[3] if 'A' in avatar_image.getbands() else None
        background.paste(avatar_image, (x, y), mask)

        text_x, text_y = text_offsets[index]
        draw.text((text_x, text_y), f"{score} Wins", font=fonts[index], fill='#553EF9')

    file_path = 'leaderboards/leaderboard_with_avatars.png'
    background.save(file_path)
    return file_path


is_git_repo_up_to_date()
client.run(BOT_TOKEN)

