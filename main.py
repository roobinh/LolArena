import os, json, random, discord, subprocess
from dotenv import dotenv_values
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from discord.ext.commands import MissingPermissions
from datetime import datetime

# List of League of Legends champions
lol_champions = [
    "Aatrox", "Ahri", "Akali", "Alistar", "Amumu", "Anivia", "Annie", "Aphelios", "Ashe", "Aurelion Sol",
    "Azir", "Bard", "Blitzcrank", "Brand", "Braum", "Caitlyn", "Camille", "Cassiopeia", "Cho'Gath",
    "Corki", "Darius", "Diana", "Dr. Mundo", "Draven", "Ekko", "Elise", "Evelynn", "Ezreal", "Fiddlesticks",
    "Fiora", "Fizz", "Galio", "Gangplank", "Garen", "Gnar", "Gragas", "Graves", "Hecarim", "Heimerdinger",
    "Illaoi", "Irelia", "Ivern", "Janna", "Jarvan IV", "Jax", "Jayce", "Jhin", "Jinx", "Kai'Sa",
    "Kalista", "Karma", "Karthus", "Kassadin", "Katarina", "Kayle", "Kayn", "Kennen", "Kha'Zix", "Kindred",
    "Kled", "Kog'Maw", "LeBlanc", "Lee Sin", "Leona", "Lillia", "Lissandra", "Lucian", "Lulu", "Lux",
    "Malphite", "Malzahar", "Maokai", "Master Yi", "Miss Fortune", "Mordekaiser", "Morgana", "Nami", "Nasus", "Nautilus",
    "Neeko", "Nidalee", "Nocturne", "Nunu & Willump", "Olaf", "Orianna", "Ornn", "Pantheon", "Poppy", "Pyke",
    "Qiyana", "Quinn", "Rakan", "Rammus", "Rek'Sai", "Rell", "Renekton", "Rengar", "Riven", "Rumble",
    "Ryze", "Samira", "Sejuani", "Senna", "Seraphine", "Sett", "Shaco", "Shen", "Shyvana", "Singed",
    "Sion", "Sivir", "Skarner", "Sona", "Soraka", "Swain", "Sylas", "Syndra", "Tahm Kench", "Taliyah",
    "Talon", "Taric", "Teemo", "Thresh", "Tristana", "Trundle", "Tryndamere", "Twisted Fate", "Twitch", "Udyr",
    "Urgot", "Varus", "Vayne", "Veigar", "Vel'Koz", "Vi", "Viego", "Viktor", "Vladimir", "Volibear",
    "Warwick", "Wukong", "Xayah", "Xerath", "Xin Zhao", "Yasuo", "Yone", "Yorick", "Yuumi", "Zac",
    "Zed", "Ziggs", "Zilean", "Zoe", "Zyra","Gwen", "Akshan", "Vex", "Zeri", "Renata Glasc", "Bel'veth", 
    "Nilah", "K'sante", "Milio", "Naafiri", "Briar", "Hwei", "Smolder"
]

env = dotenv_values('.env')
bot_token = env.get('BOT_TOKEN_DEV') or env.get('BOT_TOKEN')

intents = discord.Intents.all()
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)
# Dictionary to store assigned numbers to players
player_numbers = {}
wins_file = "champion_wins.json"

class AddChampionModal(Modal):
    def __init__(self, user_id):
        super().__init__(title="Add a Champion to Your Win List")
        self.user_id = user_id
        self.champion_input = TextInput(label="Champion Name", placeholder="e.g., Ahri, Zed")
        self.add_item(self.champion_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Retrieve the entered champion name
        entered_champion = self.champion_input.value.strip()
        entered_champion = next((champion for champion in lol_champions if champion.lower() == entered_champion.lower()), entered_champion)
        print(f'entered_champion = {entered_champion}')

        # Validate the entered champion against the predefined list
        if entered_champion not in lol_champions:
            await interaction.response.send_message(
                f"Champion **{entered_champion}** not found in the available champion list.",
                ephemeral=True
            )
            return

        # Load existing wins data
        champion_wins = load_champion_wins()

        # Update or create the entry for the user, ensuring the 'wins' key always exists
        user_key = str(self.user_id)
        if user_key not in champion_wins:
            champion_wins[user_key] = {"name": interaction.user.name, "wins": []}
        elif "wins" not in champion_wins[user_key]:
            champion_wins[user_key]["wins"] = []

        # Check if the champion is already in the user's wins
        existing_champions = [win["champion"] for win in champion_wins[user_key]["wins"]]
        if entered_champion not in existing_champions:
            # Add the new win only if it doesn't already exist
            champion_wins[user_key]["wins"].append({
                "champion": entered_champion,
                "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M")
            })
            save_champion_wins(champion_wins)
            status_message = f"**{entered_champion}** successfully added to your win-list."
        else:
            status_message = f"**{entered_champion}** is already in your win-list."

        # Respond with a confirmation message
        await interaction.response.send_message(
            status_message,
            ephemeral=True
        )

class AddChampionView(View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

        # Create the "Add Champion" button and set its callback
        add_button = Button(
            label="Add",
            style=discord.ButtonStyle.success
        )
        add_button.callback = self.add_champion_callback
        self.add_item(add_button)

    async def add_champion_callback(self, interaction: discord.Interaction):
        # Show the modal to add a champion
        await interaction.response.send_modal(AddChampionModal(self.user_id))


class ArenaHelpView(View):
    def __init__(self, ctx):
        super().__init__()
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
        super().__init__()
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
        super().__init__()
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
        await generate_champions(self.ctx, interaction, self.reroll_count, self.max_rerolls, self.teammate_name)

    async def next_game(self, interaction: discord.Interaction):
        clicked_user = interaction.user.name
        await interaction.response.defer()
        await generate_champions(self.ctx, None, 0, 2, clicked_user)

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
    def __init__(self, user_id):
        super().__init__(title="Remove a Champion from Your Win List")
        self.user_id = user_id
        self.champion_input = TextInput(label="Champion Name", placeholder="e.g., Ahri, Zed")
        self.add_item(self.champion_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Retrieve the entered champion name
        entered_champion = self.champion_input.value.strip()
        entered_champion = next((champion for champion in lol_champions if champion.lower() == entered_champion.lower()), entered_champion)
        
        # Load existing wins data
        champion_wins = load_champion_wins()

        # Remove the entered champion from the user's list
        user_key = str(self.user_id)
        if user_key in champion_wins and "wins" in champion_wins[user_key]:
            original_count = len(champion_wins[user_key]["wins"])
            champion_wins[user_key]["wins"] = [
                win for win in champion_wins[user_key]["wins"] if win["champion"] != entered_champion
            ]
            save_champion_wins(champion_wins)

            # Check if a champion was actually removed
            if entered_champion.lower() not in [champ.lower() for champ in lol_champions]:
                status_message = f"**{entered_champion}** is not a champion."
            elif len(champion_wins[user_key]["wins"]) < original_count:
                status_message = f"**{entered_champion}** has been removed from your win-list."
            else:
                status_message = f"**{entered_champion}** is not in your win-list."
        else:
            status_message = f"**{entered_champion}** is not in your win-list."

        # Respond with a confirmation message
        await interaction.response.send_message(status_message, ephemeral=True)


class RemoveChampionView(View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

        # Create the "Remove Champion" button and set its callback
        remove_button = Button(label="Remove", style=discord.ButtonStyle.danger)
        remove_button.callback = self.remove_champion_callback
        self.add_item(remove_button)

    async def remove_champion_callback(self, interaction: discord.Interaction):
        # Show the modal to remove a champion
        await interaction.response.send_modal(RemoveChampionModal(self.user_id))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("I don't have permission to do that. Please check my role permissions.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CommandInvokeError):
        await ctx.send("An error occurred while executing the command. Make sure I have the necessary permissions.")
    else:
        await ctx.send(f"An unexpected error occurred: {error}")

@bot.hybrid_command(
    name="arena",
    description="Generate random teams or champions based on specified criteria"
)
async def arena(ctx, mode: str = "", username: str = ""):
    mode = mode.lower()
    if mode == "help":
        await list_commands(ctx)
    if mode == "leaderboard":
        await list_leaderboard(ctx)
    elif mode in ["champions", "champion", "c"]:
        if username:
            target_user = discord.utils.get(ctx.guild.members, name=username)
            if target_user:
                await generate_champions(ctx, None, 0, 2, target_user.name)
            else:
                await ctx.send(f"User **{username}** not found.")
        else:
            await generate_champions(ctx)
    elif mode in ["wins", "win", "w"]:
        if username:
            target_user = discord.utils.get(ctx.guild.members, name=username)
            if target_user:
                await list_wins(ctx, target_user)
            else:
                await ctx.send(f"User **{username}** not found.")
        else:
            await list_wins(ctx)
    elif mode in ["list", "players", "player"]:
        await list_players(ctx)
    else:
        if mode.isdigit():
            await generate_teams(ctx, mode)
        else:
            await generate_teams(ctx)


# Helper function to load or initialize the wins data
def load_champion_wins():
    if os.path.exists(wins_file):
        try:
            with open(wins_file, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return {}
    return {}

# Helper function to save the wins data
def save_champion_wins(data):
    with open(wins_file, "w") as file:
        json.dump(data, file, indent=4)

async def list_wins(ctx, target_user=None):
    if target_user:
        user_key = str(target_user.id)
        user_name = target_user.name
    else:
        user_key = str(ctx.author.id)
        user_name = ctx.author.name

    # Load the current wins data
    champion_wins = load_champion_wins()
    total_wins = 0

    if user_key in champion_wins and "wins" in champion_wins[user_key]:
        wins = champion_wins[user_key]["wins"]
        total_wins = len(wins)
        if wins:
            wins_str = "\n".join([f"• **{win['champion']}** (_{win['timestamp']}_)" for win in wins])
        else:
            wins_str = "The win list is currently empty 🥲"
    else:
        wins_str = "The win list is currently empty 🥲"

    embed = discord.Embed(
        title=f"{user_name}'s Win List ({total_wins}) 👑",
        description=wins_str,
        color=discord.Color.green()
    )

    # Add Remove and Add Champion buttons
    view = View()
    view.add_item(RemoveChampionView(user_key).children[0])  # Get the Remove button
    view.add_item(AddChampionView(user_key).children[0])  # Get the Add button

    await ctx.send(embed=embed, view=view)

async def list_leaderboard(ctx):
    wins_file = load_champion_wins()
    leaderboard = {}

    for info in wins_file.values():
        user = discord.utils.get(ctx.guild.members, name=info['name'])
        if user:
            leaderboard[info['name']] = len(info['wins'])

    leaderboard = dict(sorted(leaderboard.items()))

    embed = discord.Embed(
        title="Leaderboard 🏆",
        description="\n".join([f"**{name}**:{total} wins" for name,total in leaderboard.items()]),
        color=discord.Color.orange()
    )

    view = View()
    await ctx.send(embed=embed, view=view)

async def list_commands(ctx):
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
    await ctx.send(embed=embed, view=ArenaHelpView(ctx))


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
        await ctx.send("You need to be in a voice channel to use this command!")

async def generate_teams(ctx, arg=None):
    if ctx.author.voice and ctx.author.voice.channel:
        voice_channel = ctx.author.voice.channel
        members = [member for member in voice_channel.members if not member.bot]
        member_names = [member.name for member in members]

        if arg and arg.isdigit():
            selected_players = [member for member in members if player_numbers.get(member.id) in map(int, arg)]
        else:
            selected_players = members

        if len(selected_players) == 0:
            await ctx.send("No players match these numbers. Check `/arena list` for more information.")
        else:
            random.shuffle(selected_players)
            teams = []
            while len(selected_players) > 1:
                team = [selected_players.pop().name, selected_players.pop().name]
                teams.append(team)
            if selected_players:
                solo = selected_players.pop().name
                teams.append([solo])

            embed = discord.Embed(
                title="Teams for Arena",
                description="\n".join([f"Team {i+1}: {', '.join(team)}" for i, team in enumerate(teams)]),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
    else:
        await ctx.send("You need to be in a voice channel to use this command!")

async def generate_champions(ctx, interaction=None, reroll_count=0, max_rerolls=2, teammate_name=None):
    teammate_name = None if teammate_name == "Teammate" else teammate_name
    user_id = ctx.author.id
    author = ctx.author.name

    champion_wins = load_champion_wins()
    user_wins = [win["champion"] for win in champion_wins.get(str(user_id), {}).get("wins", [])]
    available_for_user = [champion for champion in lol_champions if champion not in user_wins]
    if not available_for_user:
        await ctx.send(f"{author}, you have won with all available champions.")
        return
    user_champion = random.choice(available_for_user)

    if teammate_name:
        target_user = discord.utils.get(ctx.guild.members, name=teammate_name)
        if not target_user:
            await ctx.send(f"User **{teammate_name}** not found.")
            return
        teammate_id = target_user.id
        teammate_name_actual = teammate_name
        teammate_wins = [win["champion"] for win in champion_wins.get(str(teammate_id), {}).get("wins", [])]
        available_for_teammate = [champion for champion in lol_champions if champion not in teammate_wins]
        if not available_for_teammate:
            await ctx.send(f"{teammate_name_actual}, you have won with all available champions.")
            return
        teammate_champion = random.choice(available_for_teammate)
    else:
        teammate_name_actual = "Teammate"
        available_for_teammate = [champion for champion in lol_champions if champion != user_champion]
        teammate_champion = random.choice(available_for_teammate)

    def clean_name(name):
        return name.lower().replace("'", "").replace(" ", "")

    user_champion_url = f"https://blitz.gg/lol/champions/{clean_name(user_champion)}/arena"
    teammate_champion_url = f"https://blitz.gg/lol/champions/{clean_name(teammate_champion)}/arena"

    user_hyperlink = f"[{user_champion}]({user_champion_url})"
    teammate_hyperlink = f"[{teammate_champion}]({teammate_champion_url})"

    embed = discord.Embed(
        title="Random Champions",
        description=f"{author}: {user_hyperlink}\n{teammate_name_actual}: {teammate_hyperlink}",
        color=discord.Color.orange()
    )

    if interaction:
        await interaction.response.edit_message(embed=embed, view=ChampionButtonView(ctx, [user_champion, teammate_champion], reroll_count, max_rerolls, teammate_name_actual))
    else:
        await ctx.send(embed=embed, view=ChampionButtonView(ctx, [user_champion, teammate_champion], reroll_count, max_rerolls, teammate_name_actual))

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

is_git_repo_up_to_date()
bot.run(bot_token)
