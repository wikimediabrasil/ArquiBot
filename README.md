# ArquiBot

Arquibot is a Wikipedia archive bot built with Django for the Brazilian Wikimedia community.

It monitors Portuguese Wikipedia (ptwiki) for new or unarchived external links in {{citar}} templates, automatically archives them using the Wayback Machine, and updates the articles with properly formatted archived citations. The bot also logs statistics into a Django database and provides a web interface for monitoring activity.

## Running locally

Enter the `arquibot/` directory.

Copy `.env.sample` to `.env` and provide the environment variables.

To authenticate it locally, you will need to use the developer access. Request an access token at <https://api.wikimedia.org/wiki/Special:AppManagement>, click on "Create key". You should ask for a **Personal API token**, allow it to create and edit items and save. Copy the **Access token** to fill `ARQUIBOT_TOKEN`.

Setup a python virtual environment using `requirements.txt`.

### Available commands

* `python3 manage.py runserver` to see the web page with statistics
* `python3 manage.py run_archive_bot` to run for recent changes withing the last 24 hours
* `python3 manage.py run_article TITLE` to run for a specific article

## FEATURES

Monitors recent changes on Portuguese Wikipedia

Detects {{citar}} citations with missing archive fields

Checks whether links are alive or dead (HTTP 200 vs errors)

Archives unarchived links via the Wayback Machine API

Inserts fields (arquivourl, arquivodata, urlmorta) in citations

Skips citations already archived

Saves actions into an ArchiveLog model for statistics

Exposes a simple HTML dashboard (stats.html)

Runs as a Django management command and time interval can be scheduled

HOW TO USE

1. Clone the repository

2. Create and activate a virtual environment

3. Install dependencies using "pip install -r requirements.txt"

4. Set up all environment variables(check the settings.py file). Create a .env file in the project root with your Wikimedia API token (to allow for editing articles):

    ARQUIBOT_TOKEN=your_wikimedia_oauth_token_here

    Then go to the settings.py file and add your preferred int values for the variables

5. Run database migrations

6. Run "python manage.py run_archive_bot" . This command will:

   Fetch recent changes from Portuguese Wikipedia

   Parse {{citar}} citations

   Archive unarchived links

   Log results in the database and log file

7. Start the Django development server by running: "python manage.py runserver"

8. Visit http://localhost:8000 to see logged archiving statistics.
