import os, json, random, discord, subprocess, requests
from typing import List
from dotenv import dotenv_values
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

def load_champion_list(file_path="lol_champions.json"):
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

# Get tokens
env = dotenv_values('.env')
BOT_TOKEN = env.get('BOT_TOKEN_DEV') or env.get('BOT_TOKEN')
GUILD_ID = env.get("GUILD_ID", None)

# Bot Variables
intents = discord.Intents.all()
intents.voice_states = True
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


class TeamMemberSelectionView(discord.ui.View):
    def __init__(self, members):
        super().__init__()
        # Create the select menu and add it to the view
        self.add_item(TeamMemberSelectMenu(members))


class TeamMemberSelectMenu(discord.ui.Select):
    def __init__(self, members):
        options = [
            discord.SelectOption(label=member.name, value=str(member.id)) for member in members 
        ]
        super().__init__(
            placeholder="Select members for the team...",
            min_values=2,  # Minimum number of selections
            max_values=len(options),  # Maximum number of selections
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_members = [discord.utils.get(interaction.guild.members, id=int(member_id)) for member_id in self.values]
        random.shuffle(selected_members)
        teams = [selected_members[i:i + 2] for i in range(0, len(selected_members), 2)]
        if len(selected_members) % 2 == 1:
            teams[-1].append('Solo player: ' + teams[-1].pop().name)  # Using `name` instead of `display_name`
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
        await interaction.response.defer()
        await generate_champions(interaction, 0, 2, self.teammate_name, True)

    async def game_win(self, interaction: discord.Interaction):
        clicked_user = interaction.user
        if clicked_user != self.teammate_name:
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


# Helper function to save the wins data
def save_champion_wins(data):
    with open(WINS_FILE, "w") as file:
        json.dump(data, file, indent=4)

async def get_wins_embed_and_view(interaction, target_user=None):
    # If no target user is specified, use the user who initiated the interaction
    user_key = str(target_user.id) if target_user else str(interaction.user.id)
    user_name = target_user.name if target_user else interaction.user.name

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
    wins_data = load_champion_wins()
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
    WINS_FILE = load_champion_wins()
    leaderboard = {}

    for info in WINS_FILE.values():
        user = discord.utils.get(interaction.guild.members, name=info['name'])
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
    description="Generate 2 random champions NEW",
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
        # Collect all non-bot members for selection
        members = [member for member in interaction.guild.members if not member.bot]
        if members:
            view = TeamMemberSelectionView(members)
            await interaction.response.send_message("Select members for your teams:", view=view)
        else:
            await interaction.response.send_message("No members available for selection.", ephemeral=True)
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
                    solo_player_display = 'Solo player: ' + solo_player.name

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



async def generate_champions(interaction: discord.Interaction, reroll_count=0, max_rerolls=2, teammate_name=None, is_next_game=False):
    author = interaction.user.name 
    user_id = interaction.user.id  
    teammate_name = None if teammate_name == "Teammate" else teammate_name
    if teammate_name == author:
        await interaction.response.send_message("You can not team up with yourself.", ephemeral=True)
        return

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
        {"coords": (630, 250, 105, 105), "text_offset": (640, 420)}   # Third place
    ]

    draw = ImageDraw.Draw(background)
    print(f"leaderboard_data = {leaderboard_data}")
    sorted_leaderboard = sorted(leaderboard_data.items(), key=lambda item: item[1], reverse=True)[:3]
    print(f"sorted_leaderboard = {sorted_leaderboard}")
    
    for index, ((user_id, score), (avatar_url, username)) in enumerate(zip(sorted_leaderboard, avatar_info)):
        avatar_image = Image.open(BytesIO(requests.get(avatar_url).content) if avatar_url.startswith('http') else avatar_url)
        avatar_image = avatar_image.convert('RGBA').resize((config[index]["coords"][2], config[index]["coords"][3]))
        mask = avatar_image.split()[3] if 'A' in avatar_image.getbands() else None
        background.paste(avatar_image, config[index]["coords"][:2], mask)
        draw.text(config[index]["text_offset"], f"{score} Wins", font=fonts[index], fill='#553EF9')

    file_path = 'leaderboards/leaderboard_with_avatars.png'
    background.save(file_path)
    return file_path


@tree.command(name='sync', description='Owner only')
async def sync(interaction: discord.Interaction):
    print(interaction.user.id)
    print(env.get("OWNER_ID"))
    if str(interaction.user.id) == env.get("OWNER_ID"):
        await tree.sync()
        await interaction.response.send_message('✅ Command tree synced', ephemeral=True)
    else:
        await interaction.response.send_message('You must be the owner to use this command!', ephemeral=True)


@client.event
async def on_ready():
    if GUILD_ID:
        # Register commands to a specific guild for debugging
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
    else:
        # Register commands globally for production
        synced = await tree.sync()
    print(f"{len(synced)} commands have been registered {'globally' if GUILD_ID is None else 'to guild ' + GUILD_ID}")

    
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

# Check github status
github_status()

# Start the program
client.run(BOT_TOKEN)

