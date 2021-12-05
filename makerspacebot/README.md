# makerspacebot
Installation:
1. Clone the makerspacebot repo from github into apps folder
git clone https://github.com/jiemichong/makerspacebot.git

2. Install the required packages.
If using pip:
pip install --upgrade google-api-python-client gspread oauth2client google-auth-httplib2 google-auth-oauthlib

If using pip3:
pip3 install --upgrade google-api-python-client gspread oauth2client google-auth-httplib2 google-auth-oauthlib

Activating the bot:
1. Enter the virtual environment
cd ~/apps
. ~/apps/env/bin/activate

2. Run the bot from the terminal
python makerspacebot.py


Using the Telegram bot (Not an admin):
1. Go to t.me/mkrspaceAppsBot on Telegram.

2. Type /start

Adding people to Admin: 
1. Add telegram username to Admins, without the @. E.g. ADMINS = ["myusername"]


