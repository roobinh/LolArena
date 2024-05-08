## README

# Discord Arena Bot

This project is a Python-based Discord bot designed to help create randomized teams or assign League of Legends champions for players within a Discord voice channel. The bot leverages the `discord.py` library and uses buttons for intuitive interaction. It includes commands to generate teams, list players, and more.

### Features
- **Random Team Generation**: Create random teams from the members in a voice channel (even if not everyone in the voice channel is participating)
<img src="https://github.com/roobinh/LolArena/blob/main/md-images/team%20generation.png" alt="Team Generation" width="300"/>

- **Champion Assignment**: Assign 2 random champions to a team with reroll functionality.
<img src="https://github.com/roobinh/LolArena/blob/main/md-images/champions.png" alt="Random Champions Generation" width="300"/>

- **Command Buttons**: Utilize interactive buttons for ease of use.
- **Help Menu**: Provide an embedded help menu listing available commands.
<img src="https://github.com/roobinh/LolArena/blob/main/md-images/helpmenu.png" alt="Help Menu" width="400"/>

### Prerequisites
1. Python 3.8+
2. Discord Bot Token
3. Required Python libraries

### Installation

1. **Create a Discord Bot**  
   To create and configure your Discord bot:

   - Visit the [Discord Developer Portal](https://discord.com/developers/applications?new_application=true) and click on "New Application."
   - Enter a name for your application and click "Create."
   - In the left sidebar, go to the "Bot" ensure the "Message Content Intent" is enabled under the "Privileged Gateway Intents" section. This setting allows the bot to read message content.

   To invite your bot to your server:

   - In the left sidebar, go to "OAuth2" and scroll down to the "OAuth2 URL Generator."
   - Select "bot" under the "Scopes" section.
   - In the "Bot Permissions" section, select "Send Messages" and "Read Message History."
   - Copy the generated URL and paste it into your browser. You can then follow the instructions to invite your bot to your server.


1. **Clone the Repository**  
   Clone or download this project to your local machine:
   ```bash
   git clone <your-repo-url>

2. **Install Dependencies**  
   Navigate to the project's root directory and install the required libraries directly:
   ```bash
   pip install -r requirements.txt

3. **Configuration**  
   An `example.env` file has been included in the project's root directory. Rename this file to `.env` and update the `BOT_TOKEN` field with your Discord bot token:

   ```text
   BOT_TOKEN=<DISCORD_BOT_TOKEN>

4. **Run the Bot**
   Start the bot by running the Python script:
   ```bash
   python main.py

### Usage

1. **Invite the Bot to Your Server**  
   Ensure your bot has the correct permissions when invited.

2. **Commands and Usage**  
   - `/arena`: Generate random teams from players in a voice channel.
   - `/arena list`: List all players currently in a voice channel with their number.
   - `/arena champions`: Assign random League of Legends champions.
   - `/arena help`: Display a help message with all available commands.

3. **Interactive Buttons**  
   Use the buttons provided by the bot to generate teams or champions.

### Contribution
If you'd like to contribute, please fork the repository and submit a pull request. For major changes, consider opening an issue to discuss them first.

